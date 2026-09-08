#!/usr/bin/env python3

import os
import sys

from hostit_dns import HostItDNSClient, load_env_file


load_env_file()


def main():
    domain = os.getenv("CERTBOT_DOMAIN")
    validation = os.getenv("CERTBOT_VALIDATION")
    dns_zone = os.getenv("HOST_DNS_ZONE")

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

    print(f"Creating DNS-01 challenge for {domain}...")
    print(f"DNS zone: {dns_zone}")

    record_name = f"_acme-challenge.{domain}."

    print(f"Record:   {record_name}")

    client = HostItDNSClient()

    created = client.create_record(
        domain=dns_zone,
        name=record_name,
        record_type="TXT",
        content=f'"{validation}"',
        ttl=300,
    )

    if created:
        print("DNS-01 TXT record created successfully.")
    else:
        print("DNS-01 TXT record already exists; skipping create.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
