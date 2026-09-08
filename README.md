# Host.it DNS API Client

Unofficial Python client and Certbot hooks for managing DNS records through the [Host.it](https://www.host.it/) public API.

Use it to:

- authenticate with Host.it SSO
- read a DNS zone
- create and delete individual DNS records
- check whether a specific record exists
- run a safe CRUD smoke test
- automate Let's Encrypt **DNS-01** challenges (native Certbot or Docker)

This project is **not** affiliated with Host.it. The API may change without notice.

## Requirements

- Python 3.9+
- A Host.it account that can manage the target DNS zone
- [`requests`](https://pypi.org/project/requests/)
- Being enabled by Host.it to perform calls against their API

## Installation

```bash
git clone https://github.com/larss/hostit-dns-api.git
cd hostit-dns-api

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env`:

```bash
HOST_USERNAME=your_hostit_username
HOST_PASSWORD=your_hostit_password
HOST_DNS_ZONE=example.com
```

The client loads `.env` from the project directory (next to `hostit_dns.py`) and does **not** override variables already set in the environment. No `python-dotenv` dependency is required.

## CLI usage

```bash
python3 hostit_dns.py get example.com

python3 hostit_dns.py create example.com \
  --name www \
  --type A \
  --content 203.0.113.10 \
  --ttl 3600

python3 hostit_dns.py exists example.com \
  --name _acme-challenge.example.com. \
  --type TXT \
  --content '"some-token"'

python3 hostit_dns.py delete example.com \
  --name _acme-challenge.example.com. \
  --type TXT \
  --content '"some-token"'

python3 hostit_dns.py test example.com
```

`create` is idempotent: if an identical record already exists, it skips the POST.

`delete` removes **only** the matching name/type/content value. Other TXT values on the same name are left untouched (important for multi-SAN / concurrent DNS-01 challenges).

## Certbot (native)

Hooks use `#!/usr/bin/env python3`. The Python that Certbot invokes must be able to import `requests` and find `hostit_dns.py` on `PYTHONPATH` (or run the hooks from this directory).

```bash
export HOST_USERNAME=...
export HOST_PASSWORD=...
export HOST_DNS_ZONE=example.com

# Optional if hooks are not run from this directory:
export PYTHONPATH=/path/to/hostit-dns-api

certbot certonly \
  --manual \
  --preferred-challenges dns \
  --manual-auth-hook /path/to/hostit-dns-api/certbot_authenticator.py \
  --manual-cleanup-hook /path/to/hostit-dns-api/certbot_cleanup.py \
  -d example.com \
  --email user@example.com \
  --agree-tos
```

For wildcards / multi-name certs, set `HOST_DNS_ZONE` to the authoritative zone (for example `example.com`) even when requesting `*.example.com` or `app.example.com`.

After the auth hook creates the TXT record, allow DNS time to propagate before Let's Encrypt checks it. If issuance fails intermittently, add a short sleep in a wrapper around the auth hook or retry.

## Certbot (Docker)

The official `certbot/certbot` image does not include `requests`. Build a small custom image:

```dockerfile
# Dockerfile.certbot (included in this repo)
FROM certbot/certbot
RUN pip install --no-cache-dir "requests>=2.31,<3"
COPY hostit_dns.py /opt/hostit-dns-api/
COPY certbot_authenticator.py /opt/hostit-dns-api/
COPY certbot_cleanup.py /opt/hostit-dns-api/
```

Example Compose service:

```yaml
services:
  certbot:
    build:
      context: .
      dockerfile: Dockerfile.certbot
    volumes:
      - ./certbot:/etc/letsencrypt
    env_file:
      - .env
```

Issue a certificate:

```bash
docker compose run --rm certbot certonly \
  --manual \
  --preferred-challenges dns \
  --manual-auth-hook /opt/hostit-dns-api/certbot_authenticator.py \
  --manual-cleanup-hook /opt/hostit-dns-api/certbot_cleanup.py \
  -d example.com \
  --email user@example.com \
  --agree-tos
```

`/opt/hostit-dns-api` is only the path inside the image from `Dockerfile.certbot`. Your host layout for certificates can be anything you choose.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `HOST_USERNAME` | yes | Host.it account username |
| `HOST_PASSWORD` | yes | Host.it account password |
| `HOST_DNS_ZONE` | yes (Certbot) | Authoritative zone for challenge records |
| `HOST_SSO_URL` | no | Default: `https://sso.host.it/cas/v1/tickets` |
| `HOST_API_BASE_URL` | no | Default: `https://api.host.it/public` |

Certbot also injects `CERTBOT_DOMAIN` and `CERTBOT_VALIDATION` into the hooks.

## Security notes

- Never commit `.env` or real credentials.
- Prefer a Host.it account limited to DNS management when possible.
- Store secrets via your orchestrator / `env_file`, not in compose YAML.

## License

Use and redistribute at your own risk. Add a LICENSE file if you need an explicit open-source grant for downstream packaging.
