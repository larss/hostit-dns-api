# Host.it DNS API Client

A small Python client for managing DNS records through the Host.it public API.

The project is designed to provide a simple command-line interface for:

- authenticating with Host.it
- reading a DNS zone
- creating DNS records
- deleting DNS records
- testing the complete DNS CRUD workflow

It can later be used as the foundation for automated DNS-01 / Let's Encrypt certificate management.

## Requirements

- Python 3.9+
- A Host.it account with API access

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/hostit-dns-api.git
cd hostit-dns-api
