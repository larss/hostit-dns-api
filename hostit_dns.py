#!/usr/bin/env python3

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

import requests

__version__ = "0.0.2"

DEFAULT_SSO_URL = "https://sso.host.it/cas/v1/tickets"
DEFAULT_API_BASE_URL = "https://api.host.it/public"


def load_env_file(path=None):
    """
    Load environment variables from a .env file without overriding
    variables already present in the environment.
    """
    if path is None:
        path = Path(__file__).resolve().parent / ".env"
    else:
        path = Path(path)

    if not path.exists():
        return

    for line in path.read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1]:
            if value[0] in ("'", '"'):
                value = value[1:-1]

        os.environ.setdefault(key, value)


load_env_file()


class HostItAPIError(RuntimeError):
    """Raised when the Host.it API returns an unexpected response."""


def load_configuration():
    username = os.getenv("HOST_USERNAME")
    password = os.getenv("HOST_PASSWORD")

    if not username or not password:
        raise HostItAPIError(
            "Missing credentials.\n"
            "Set HOST_USERNAME and HOST_PASSWORD in .env or the environment."
        )

    sso_url = os.getenv("HOST_SSO_URL", DEFAULT_SSO_URL)
    api_base_url = os.getenv("HOST_API_BASE_URL", DEFAULT_API_BASE_URL)

    return username, password, sso_url, api_base_url


class HostItDNSClient:
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sso_url: Optional[str] = None,
        api_base_url: Optional[str] = None,
    ):
        if username is None or password is None or sso_url is None or api_base_url is None:
            env_username, env_password, env_sso_url, env_api_base_url = load_configuration()
            username = username if username is not None else env_username
            password = password if password is not None else env_password
            sso_url = sso_url if sso_url is not None else env_sso_url
            api_base_url = api_base_url if api_base_url is not None else env_api_base_url

        self.username = username
        self.password = password
        self.sso_url = sso_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")

        self.session = requests.Session()
        self.token = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> str:
        """Authenticate against Host.it SSO and return a JWT token."""

        response = self.session.post(
            self.sso_url,
            data={
                "token": "true",
                "username": self.username,
                "password": self.password,
            },
            timeout=30,
        )

        if not response.ok:
            raise HostItAPIError(
                f"Authentication failed: HTTP {response.status_code}\n"
                f"{response.text}"
            )

        # The current SSO endpoint returns the JWT as the response body.
        token = response.text.strip()

        # Be slightly more tolerant in case the server returns a JSON string.
        try:
            parsed = response.json()
            if isinstance(parsed, str):
                token = parsed.strip()
        except ValueError:
            pass

        if not token:
            raise HostItAPIError("Authentication succeeded but no token was returned.")

        self.token = token
        return token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        if not self.token:
            self.authenticate()

        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, domain: str) -> str:
        domain = domain.rstrip(".")
        return f"{self.api_base_url}/v1/domains/dns/{domain}"

    # ------------------------------------------------------------------
    # DNS operations
    # ------------------------------------------------------------------

    def get_zone(self, domain: str) -> dict:
        """Retrieve the DNS zone for a domain."""

        response = self.session.get(
            self._url(domain),
            headers=self._headers(),
            timeout=30,
        )

        if not response.ok:
            raise HostItAPIError(
                f"GET DNS zone failed: HTTP {response.status_code}\n"
                f"{response.text}"
            )

        return response.json()

    def create_record(
        self,
        domain: str,
        name: str,
        record_type: str,
        content: str,
        ttl: int = 3600,
    ) -> bool:
        """
        Create a DNS record.

        Returns True if the record was created, False if an identical
        record already exists (idempotent for Certbot re-runs).
        """

        normalized_name = self._normalize_record_name(name, domain)
        record_type = record_type.upper()

        zone = self.get_zone(domain)
        if self.record_exists(zone, normalized_name, record_type, content):
            return False

        payload = {
            "name": normalized_name,
            "type": record_type,
            "content": content,
            "ttl": ttl,
        }

        response = self.session.post(
            self._url(domain),
            headers=self._headers(),
            json=payload,
            timeout=30,
        )

        if not response.ok:
            raise HostItAPIError(
                f"POST DNS record failed: HTTP {response.status_code}\n"
                f"{response.text}"
            )

        return True

    def delete_record(
        self,
        domain: str,
        name: str,
        record_type: str,
        content: str,
        ttl: int = 3600,
    ) -> None:
        """Delete a specific DNS record value (does not remove other TXT values)."""

        payload = {
            "name": self._normalize_record_name(name, domain),
            "type": record_type.upper(),
            "content": content,
            "ttl": ttl,
        }

        response = self.session.delete(
            self._url(domain),
            headers=self._headers(),
            json=payload,
            timeout=30,
        )

        if not response.ok:
            raise HostItAPIError(
                f"DELETE DNS record failed: HTTP {response.status_code}\n"
                f"{response.text}"
            )

    def create_txt_record(
        self,
        domain: str,
        value: str,
        ttl: int = 300,
    ) -> bool:
        """Create an ACME-style TXT record."""

        return self.create_record(
            domain=domain,
            name="_acme-challenge",
            record_type="TXT",
            content=f'"{value}"',
            ttl=ttl,
        )

    def delete_txt_record(
        self,
        domain: str,
        value: str,
        ttl: int = 300,
    ) -> None:
        """Delete an ACME-style TXT record."""

        self.delete_record(
            domain=domain,
            name="_acme-challenge",
            record_type="TXT",
            content=f'"{value}"',
            ttl=ttl,
        )

    # ------------------------------------------------------------------
    # Record helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_record_name(name: str, domain: str) -> str:
        """
        Convert a record name into a fully qualified domain name.

        Examples:

            _acme-challenge
                -> _acme-challenge.example.com.

            _acme-challenge.example.com
                -> _acme-challenge.example.com.

            _acme-challenge.example.com.
                -> _acme-challenge.example.com.

            @
                -> example.com.
        """

        domain = domain.rstrip(".")
        name = name.strip()

        if name == "@":
            return f"{domain}."

        if name.endswith("."):
            return name

        if name == domain or name.endswith(f".{domain}"):
            return f"{name}."

        return f"{name}.{domain}."

    @staticmethod
    def record_exists(
        zone: dict,
        name: str,
        record_type: str,
        content: str,
    ) -> bool:
        """Check whether a specific DNS record exists in a zone."""

        expected_name = name.rstrip(".") + "."
        expected_type = record_type.upper()

        for rrset in zone.get("rrsets", []):
            rrset_name = rrset.get("name", "").rstrip(".") + "."
            rrset_type = rrset.get("type", "").upper()

            if rrset_name != expected_name or rrset_type != expected_type:
                continue

            for record in rrset.get("records", []):
                if record.get("content") == content:
                    return True

        return False


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------


def command_get(client: HostItDNSClient, args) -> None:
    zone = client.get_zone(args.domain)

    print(json.dumps(zone, indent=2, ensure_ascii=False))


def command_create(client: HostItDNSClient, args) -> None:
    name = client._normalize_record_name(args.name, args.domain)

    print(f"Creating {args.type.upper()} record:")
    print(f"  Name:    {name}")
    print(f"  Content: {args.content}")
    print(f"  TTL:     {args.ttl}")

    created = client.create_record(
        domain=args.domain,
        name=args.name,
        record_type=args.type,
        content=args.content,
        ttl=args.ttl,
    )

    if created:
        print("Record created successfully.")
    else:
        print("Record already exists; skipping.")


def command_delete(client: HostItDNSClient, args) -> None:
    name = client._normalize_record_name(args.name, args.domain)

    print(f"Deleting {args.type.upper()} record:")
    print(f"  Name:    {name}")
    print(f"  Content: {args.content}")

    client.delete_record(
        domain=args.domain,
        name=args.name,
        record_type=args.type,
        content=args.content,
        ttl=args.ttl,
    )

    print("Record deleted successfully.")


def command_exists(client: HostItDNSClient, args) -> int:
    name = client._normalize_record_name(args.name, args.domain)
    zone = client.get_zone(args.domain)
    found = client.record_exists(zone, name, args.type, args.content)

    if found:
        print(f"Record exists: {name} {args.type.upper()} {args.content}")
        return 0

    print(f"Record not found: {name} {args.type.upper()} {args.content}")
    return 1


def command_test(client: HostItDNSClient, args) -> None:
    """
    Execute a complete GET -> POST -> GET -> DELETE -> GET test.

    A temporary TXT record is created and removed automatically.
    """

    domain = args.domain.rstrip(".")
    unique_id = str(uuid.uuid4())

    test_name = f"_api-test-{unique_id}"
    test_fqdn = f"{test_name}.{domain}."
    test_content = f'"hostit-dns-api-test-{unique_id}"'
    test_ttl = 300

    created = False

    print()
    print("=" * 60)
    print("Host.it DNS API test")
    print("=" * 60)

    try:
        print("\n[1/6] Authenticating...")
        client.authenticate()
        print("      OK")

        print("\n[2/6] Reading DNS zone...")
        client.get_zone(domain)
        print("      OK")

        print("\n[3/6] Creating temporary TXT record...")
        print(f"      {test_fqdn}")

        created_now = client.create_record(
            domain=domain,
            name=test_name,
            record_type="TXT",
            content=test_content,
            ttl=test_ttl,
        )

        created = True
        print("      OK" if created_now else "      OK (already present)")

        print("\n[4/6] Verifying record...")
        verification_zone = client.get_zone(domain)

        if not client.record_exists(
            verification_zone,
            test_fqdn,
            "TXT",
            test_content,
        ):
            raise HostItAPIError(
                "The record was created but could not be found in the DNS zone."
            )

        print("      OK")

    finally:
        if created:
            print("\n[5/6] Deleting temporary TXT record...")

            try:
                client.delete_record(
                    domain=domain,
                    name=test_name,
                    record_type="TXT",
                    content=test_content,
                    ttl=test_ttl,
                )
                print("      OK")

            except Exception as exc:
                print(f"      WARNING: deletion failed: {exc}", file=sys.stderr)

    print("\n[6/6] Verifying deletion...")

    final_zone = client.get_zone(domain)

    if client.record_exists(
        final_zone,
        test_fqdn,
        "TXT",
        test_content,
    ):
        raise HostItAPIError(
            "The temporary record still exists after deletion."
        )

    print("      OK")

    print()
    print("=" * 60)
    print("TEST COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print()
    print("Authentication:       OK")
    print("Initial GET:          OK")
    print("POST creation:        OK")
    print("GET verification:     OK")
    print("DELETE:               OK")
    print("GET deletion:         OK")
    print()
    print("No permanent DNS records were modified.")
    print()


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Host.it DNS API client"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    get_parser = subparsers.add_parser(
        "get",
        help="Retrieve a DNS zone",
    )
    get_parser.add_argument(
        "domain",
        help="Domain name, e.g. example.com",
    )

    create_parser = subparsers.add_parser(
        "create",
        help="Create a DNS record",
    )
    create_parser.add_argument("domain")
    create_parser.add_argument(
        "--name",
        required=True,
        help="Record name, e.g. _acme-challenge",
    )
    create_parser.add_argument(
        "--type",
        required=True,
        help="DNS record type, e.g. TXT, A, CNAME",
    )
    create_parser.add_argument(
        "--content",
        required=True,
        help="Record content",
    )
    create_parser.add_argument(
        "--ttl",
        type=int,
        default=3600,
        help="TTL in seconds (default: 3600)",
    )

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a DNS record",
    )
    delete_parser.add_argument("domain")
    delete_parser.add_argument(
        "--name",
        required=True,
    )
    delete_parser.add_argument(
        "--type",
        required=True,
    )
    delete_parser.add_argument(
        "--content",
        required=True,
    )
    delete_parser.add_argument(
        "--ttl",
        type=int,
        default=3600,
    )

    exists_parser = subparsers.add_parser(
        "exists",
        help="Check whether a specific DNS record exists",
    )
    exists_parser.add_argument("domain")
    exists_parser.add_argument(
        "--name",
        required=True,
        help="Record name, e.g. _acme-challenge.example.com.",
    )
    exists_parser.add_argument(
        "--type",
        required=True,
        help="DNS record type, e.g. TXT",
    )
    exists_parser.add_argument(
        "--content",
        required=True,
        help='Record content, e.g. \'"some-token"\'',
    )

    test_parser = subparsers.add_parser(
        "test",
        help="Run a complete DNS API CRUD test",
    )
    test_parser.add_argument(
        "domain",
        help="Domain to use for the temporary test record",
    )

    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        client = HostItDNSClient()

        if args.command == "get":
            command_get(client, args)

        elif args.command == "create":
            command_create(client, args)

        elif args.command == "delete":
            command_delete(client, args)

        elif args.command == "exists":
            return command_exists(client, args)

        elif args.command == "test":
            command_test(client, args)

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
