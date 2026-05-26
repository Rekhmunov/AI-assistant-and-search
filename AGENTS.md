# Instructions for AI agents

## Git workflow

- **Work only on `main`.** Do not create feature branches (`cursor/*` or otherwise).
- Commit and push directly to `origin/main`.
- Do not open separate PRs unless the user explicitly asks for a PR.

## Production deploy

- Server path: `/opt/aisearch`
- Update: `bash scripts/update.sh` (from repo root)
- Secrets: `.env` only (never commit). `nginx/nginx.prod.conf` is local/generated — not tracked in git.
