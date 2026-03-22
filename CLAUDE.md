# dokploy-ctl — CLI for Dokploy deployments

Pure Python CLI (click + httpx + websockets) for deploying, polling, and debugging Dokploy services.

## Dev Commands

- Run tests: `make test`
- Lint: `make lint` or `agent-harness lint` (check only, never modifies files — safe to run anytime)
- Fix: `make fix` or `agent-harness fix` (auto-fix, then runs lint to verify)
- Full gate: `make check` (lint + test)
- Audit: `agent-harness audit` (checks project hygiene)
- Build: `make build`
- Bootstrap: `make bootstrap` (installs deps, requires `agent-harness` CLI)
- Never truncate commands with `| tail` or `| head` — output is already optimized

## Never

- Never commit `.env` files or API tokens
- Never run `dokploy-ctl` commands against production without explicit user confirmation

## Ask First

- Before changing CLI argument names or command structure (breaking change for users)
- Before adding new dependencies
