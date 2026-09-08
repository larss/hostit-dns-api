#!/usr/bin/env python3

import os
import sys

from hostit_dns import HostItDNSClient


def main() -> int:
    domain = os.environ.get("CERTBOT_DOMAIN")
    validation = os.environ.get("CERTBOT_VALIDATION")
    dns_zone = os.environ.get("HOST_DNS_ZONE")

    if not domain or not validation:
        print(
            "ERROR: CERTBOT_DOMAIN and CERTBOT_VALIDATION are required.",
            file=sys.stderr,
        )
        return 1

    if not dns_zone:
        print(
            "ERROR: HOST_DNS_ZONE is required.",
            file=sys.stderr,
        )
        return 1

    username = os.environ.get("HOST_USERNAME")
    password = os.environ.get("HOST_PASSWORD")

    if not username or not password:
        print(
            "ERROR: HOST_USERNAME and HOST_PASSWORD are required.",
            file=sys.stderr,
        )
        return 1

    client = HostItDNSClient(
        username=username,
        password=password,
        sso_url=os.environ.get(
            "HOST_SSO_URL",
            "https://sso.test.host.it/cas/v1/tickets",
        ),
        api_base_url=os.environ.get(
            "HOST_API_BASE_URL",
            "https://api.host.it/public",
        ),
    )

    record_name = f"_acme-challenge.{domain}."

    print(f"Removing DNS-01 challenge for {domain}...")
    print(f"DNS zone: {dns_zone}")
    print(f"Record:   {record_name}")

    client.delete_record(
        domain=dns_zone,
        name=record_name,
        record_type="TXT",
        content=f'"{validation}"',
        ttl=300,
    )

    print("DNS-01 TXT record deleted successfully.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
