# Deploy — Docker + existing Traefik

Runs the app as a single container that joins your existing Traefik network. Traefik
terminates TLS (Let's Encrypt, via the certresolver you already use for other services) and
enforces HTTP Basic Auth in front of the app — the app itself has no auth of its own.

## One-time setup

1. **Copy the env file and fill it in:**

   ```bash
   cp .env.example .env
   ```

2. **Find your existing Traefik network name and certresolver name.**

   ```bash
   docker network ls                       # look for the network your Traefik container joins
   ```

   The certresolver name comes from Traefik's own static configuration (its `--certificatesresolvers.<name>.acme...`
   flags, or the `certResolver` value other services' labels already use). Set both in `.env`:

   ```
   TRAEFIK_NETWORK=<your network name>
   TRAEFIK_CERT_RESOLVER=<your resolver name>
   ```

3. **Point `DOMAIN` at this server's DNS record** you've already created, e.g.
   `DOMAIN=patrimonio.example.com`.

4. **Generate the Basic Auth credential** and put it in `BASIC_AUTH_USERS`:

   ```bash
   htpasswd -nB admin
   # New password: ********
   # admin:$2y$05$...
   ```

   Paste the `user:hash` line into `.env`, **doubling every `$` to `$$`**
   (`admin:$$2y$$05$$...`). This is required: `docker compose` runs its own `${VAR}`-style
   interpolation over `.env` file *values* too, not just over `docker-compose.yml` — a lone
   `$` in `.env` gets treated as the start of a variable reference and silently truncates the
   hash at that point (verified: without doubling, `admin:$2y$05$abc...` becomes just
   `admin:$2y$05` end-to-end, both in the container's env and in the Traefik label — broken,
   with no error). One easy way to double them automatically:

   ```bash
   htpasswd -nB admin | sed 's/\$/$$/g'
   ```

   Multiple users can be comma-separated (`user1:hash1,user2:hash2`), each with its `$`
   doubled the same way.

5. **Pick where the SQLite file lives on the host** via `DATA_DIR` (default `./data`, relative
   to wherever you run `docker compose` from). The container always sees it as `/data`.

## Bring it up

```bash
docker compose config     # sanity-check labels/env substitution before touching anything
docker compose up -d --build
docker compose logs -f app   # confirm "alembic upgrade head" ran, then uvicorn started
```

## Verify

```bash
curl -I https://$DOMAIN                       # no credentials -> 401, WWW-Authenticate: Basic
curl -I -u admin:yourpassword https://$DOMAIN  # -> 200, valid TLS cert
```

If the router never shows up in Traefik: check `docker network ls` shows the app container on
the same network as Traefik (`docker inspect patrimonio | grep -A5 Networks`), and check
`TRAEFIK_NETWORK`/`TRAEFIK_CERT_RESOLVER` in `.env` actually match your Traefik instance.

## Updating

```bash
git pull
docker compose up -d --build   # rebuilds image; entrypoint runs any new Alembic migration on start
```

## Backups

The DB is one file at `${DATA_DIR}/patrimonio.db` on the host. A nightly cron entry is enough:

```bash
sqlite3 ${DATA_DIR}/patrimonio.db ".backup '/path/to/backups/patrimonio-$(date +\%F).db'"
```
