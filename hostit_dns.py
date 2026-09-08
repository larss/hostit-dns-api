#!/usr/bin/env python3

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import requests


DEFAULT_SSO_URL = "https://sso.host.it/cas/v1/tickets"
DEFAULT_API_BASE_URL = "https://api.host.it/public"

def load_env_file(path="/srv/dns_updater/.env"):
    env_path = Path(path)

    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_env_file()


class HostItAPIError(RuntimeError):
    """Raised when the Host.it API returns an unexpected response."""


class HostItDNSClient:
    def __init__(
        self,
        username: str,
        password: str,
        sso_url: str = DEFAULT_SSO_URL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ):
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
    ) -> None:
        """Create a DNS record."""

        payload = {
            "name": self._normalize_record_name(name, domain),
            "type": record_type.upper(),
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

    def delete_record(
        self,
        domain: str,
        name: str,
        record_type: str,
        content: str,
        ttl: int = 3600,
    ) -> None:
        """Delete a DNS record."""

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
    ) -> None:
        """Create an ACME-style TXT record."""

        self.create_record(
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

    client.create_record(
        domain=args.domain,
        name=args.name,
        record_type=args.type,
        content=args.content,
        ttl=args.ttl,
    )

    print("Record created successfully.")


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
        # --------------------------------------------------------------
        # Authentication
        # --------------------------------------------------------------

        print("\n[1/6] Authenticating...")
        client.authenticate()
        print("      OK")

        # --------------------------------------------------------------
        # Initial GET
        # --------------------------------------------------------------

        print("\n[2/6] Reading DNS zone...")
        initial_zone = client.get_zone(domain)
        print("      OK")

        # --------------------------------------------------------------
        # POST
        # --------------------------------------------------------------

        print("\n[3/6] Creating temporary TXT record...")
        print(f"      {test_fqdn}")

        client.create_record(
            domain=domain,
            name=test_name,
            record_type="TXT",
            content=test_content,
            ttl=test_ttl,
        )

        created = True
        print("      OK")

        # --------------------------------------------------------------
        # GET verification
        # --------------------------------------------------------------

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
        # --------------------------------------------------------------
        # DELETE
        # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # Final GET
    # --------------------------------------------------------------

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

    # GET
    get_parser = subparsers.add_parser(
        "get",
        help="Retrieve a DNS zone",
    )
    get_parser.add_argument(
        "domain",
        help="Domain name, e.g. example.com",
    )

    # CREATE
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

    # DELETE
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

    # TEST
    test_parser = subparsers.add_parser(
        "test",
        help="Run a complete DNS API CRUD test",
    )
    test_parser.add_argument(
        "domain",
        help="Domain to use for the temporary test record",
    )

    return parser


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

def main() -> int:
    try:
        args = build_parser().parse_args()

        username, password, sso_url, api_base_url = load_configuration()

        client = HostItDNSClient(
            username=username,
            password=password,
            sso_url=sso_url,
            api_base_url=api_base_url,
        )

        if args.command == "get":
            command_get(client, args)

        elif args.command == "create":
            command_create(client, args)

        elif args.command == "delete":
            command_delete(client, args)

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
