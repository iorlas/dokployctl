# dokploy-ctl v2 — AI-Native CLI Design

## Goal

Redesign dokploy-ctl so AI agents never need to bypass the CLI. Every command is a self-contained workflow that narrates what it's doing, auto-escalates on failure, and tells the agent what to do next. Zero manual deployment tasks for the human.

## Motivation

Session data analysis (188 tool invocations across aggre/reelm/proxy-hub):
- **73 raw `api` calls** — agents constructed JSON payloads by hand because dedicated commands were missing or insufficient
- **33 library imports** — agents imported dokploy-ctl as Python module to call `get_containers()` because `status` didn't expose enough data
- **47 manual deploy chains** — agents bypassed `deploy` because it required all env vars locally, then manually did sync → deploy → poll in bash loops
- **0 uses of `status --live`** — the feature existed but agents couldn't discover it

## Design Principles

### 1. Every command is a workflow, not an operation

`deploy` doesn't just trigger — it syncs, deploys, polls, health-checks, and on failure auto-fetches logs with diagnosis. The agent never chains commands manually.

### 2. LDD output — structured narrative

Every command emits timestamped action traces:

```
[00:00] Syncing compose file (2,847 chars)...
[00:01] Synced. 2,847 chars persisted.
[00:01] Triggering deploy (Deploy main-a1b2c3d)...
[00:06] Polling... status=running
[00:11] Polling... status=done
```

Three layers in every output:
- **What I'm doing** (action trace with timestamps)
- **What happened** (result + diagnostics)
- **What to do next** (hints with exact commands on anomalies)

Timestamps are relative from command start — agents can see where time was spent and correlate with timeouts.

### 3. IDs everywhere

Every output line that references a service or container includes the compose ID and service name. Suggested commands are copy-paste ready — zero assembly.

```
Unhealthy services:
  worker  (container: a1b2c3d4)  — exited(1), 30s ago

Hint: worker failed to start. Check Dockerfile entrypoint.
  dokploy-ctl logs IWcYWttLzI --service worker --tail 200
```

Use **compose service names** as primary identifier (what agents know from docker-compose.yml), container IDs in parentheses for raw Docker use.

### 4. Hints on anomalies

When something looks wrong, the output says what's wrong and suggests the exact next command. Not just data — guidance. Examples:
- Container unhealthy → show logs, suggest `logs --service X`
- Missing healthcheck on a service → warn before deploying
- Deploy timeout → show which services are still converging
- Stale image tag → warn if using `:latest` or mutable tag

### 5. Zero-guessing discovery

Running `dokploy-ctl` with no args lists all known compose apps:

```
Compose apps:
  IWcYWttLzI  aggre         done   3 services  2m ago
  xK9pL2mN4R  proxy-hub     done   1 service   1h ago

Run: dokploy-ctl status <id> for details
```

Every error message includes the exact command to fix it.

---

## Command Changes

### `deploy` — redesigned

```
dokploy-ctl deploy <compose-id> <compose-file> [--env] [--env-file FILE] [--timeout 300]
```

**Breaking change:** env resolution is now opt-in, not default.

- **Default (no flags):** sync compose file → deploy → poll → health-check. Dokploy uses whatever env is already stored. If the compose file contains `${VAR}` refs, they are pushed as-is — Dokploy resolves them from its stored env.
- **`--env`:** scan compose for `${VAR}`, resolve all from `os.environ`, push to Dokploy alongside compose file. This is the CI mode. Exits with error if any referenced var is missing from the environment.
- **`--env-file FILE`:** read env from file instead of environment variables.
- **`--env` + `--env-file`:** error — mutually exclusive.

**Auto-escalation on failure:**

When deploy fails or containers are unhealthy, `deploy` automatically:
1. Fetches the deploy build log
2. Fetches container logs for problem services (sorted: exited → unhealthy)
3. Emits a diagnosis with service names, container IDs, and suggested next commands

```
[00:00] Syncing compose file (2,847 chars)...
[00:01] Synced. 2,847 chars persisted.
[00:01] Triggering deploy (Deploy main-a1b2c3d)...
[00:06] Polling... [1/60] status=running
[00:11] Polling... [2/60] status=error
[00:11] Deploy failed: "exit code 1"
[00:11]
[00:11] === Deploy build log ===
[00:11]   docker compose up -d ...
[00:11]   Error: service "worker" failed to start: exec /app/run.sh: no such file
[00:12]
[00:12] === Logs: worker (exited, Exited (1) 30s ago, container: a1b2c3d4) ===
[00:12]   FileNotFoundError: /app/run.sh
[00:12]
[00:12] Hint: worker failed to start. Check the Dockerfile entrypoint.
[00:12]   dokploy-ctl logs IWcYWttLzI --service worker --tail 200
[00:12]   dokploy-ctl status IWcYWttLzI
[00:12]
[00:12] Deploy failed (12s total). 1 unhealthy service.
```

### `status` — merged with `--live`

```
dokploy-ctl status <compose-id>
```

**Always shows everything** — compose config AND live containers. No `--live` flag.

Output:
```
[00:00] Fetching compose app IWcYWttLzI...

Name:         aggre
App name:     compose-connect-back-end-alarm-zgu447
Status:       done
Compose:      2,847 chars
Env keys:     IMAGE_TAG, DB_PASSWORD, HATCHET_CLIENT_TOKEN

Last deploy:  Deploy main-a1b2c3d (done)
  at:         2026-03-24T19:30:00Z

Containers:
  SERVICE          STATE      HEALTH       IMAGE                              UPTIME    CONTAINER ID
  worker           running    healthy      ghcr.io/iorlas/aggre:main-a1b2c3d  2h        a1b2c3d4
  hatchet-lite     running    healthy      ghcr.io/hatchet/hatchet:latest     2h        e5f6g7h8
  db               running    healthy      postgres:16                        2h        i9j0k1l2
  migrate          exited(0)  —            ghcr.io/iorlas/aggre:main-a1b2c3d  —         m3n4o5p6

[00:01] All 4 containers healthy (1 one-shot completed). (1s total)
```

If unhealthy containers exist, adds hints:
```
Hint: worker is unhealthy.
  dokploy-ctl logs IWcYWttLzI --service worker --since 5m
```

### `find` — new

```
dokploy-ctl find [name]
```

- `dokploy-ctl find aggre` — search by project/compose name, return matching compose IDs
- `dokploy-ctl find` (no args) — list all projects and compose apps (same as bare `dokploy-ctl`)

```
[00:00] Searching projects...

  PROJECT          COMPOSE ID    APP NAME                                    STATUS  SERVICES
  aggre            IWcYWttLzI    compose-connect-back-end-alarm-zgu447       done    4
  proxy-hub        xK9pL2mN4R    compose-transmit-haptic-application-7r6yr3  done    1
  reelm            qR3sT4uV5W    compose-navigate-digital-bridge-8xt2k9     done    3

[00:01] 3 projects, 3 compose apps. (1s total)
```

### `stop` — new

```
dokploy-ctl stop <compose-id>
```

```
[00:00] Stopping compose IWcYWttLzI...
[00:03] Stopped. Final container states:
  worker=exited(0), hatchet-lite=exited(0), db=exited(0)

Hint: To restart: dokploy-ctl start IWcYWttLzI
[00:03] Done (3s total).
```

### `start` — new

```
dokploy-ctl start <compose-id>
```

Starts the compose app, then runs the same health-check workflow as `deploy` — polls until all containers are healthy, auto-fetches logs on failure.

```
[00:00] Starting compose IWcYWttLzI...
[00:05] Verifying container health...
[00:10]   worker=starting, db=ok, hatchet-lite=starting
[00:15]   worker=ok, db=ok, hatchet-lite=ok
[00:15] All containers healthy. Started (15s total).
```

### `logs` — minor changes

```
dokploy-ctl logs <compose-id> [--service NAME] [--tail N] [--since DURATION] [-D]
```

**Change:** default `--since` from `all` to `5m`. Most debugging is recent. Use `--since all` explicitly for full history.

Output adds timestamps and service name headers with container IDs:
```
[00:00] Fetching logs for IWcYWttLzI (last 5m, tail 100)...

--- worker (container: a1b2c3d4) ---
2026-03-24T19:30:01Z  Starting worker...
2026-03-24T19:30:02Z  Connected to database
...

[00:02] Done (2s total).
```

### `init` — minor changes

Update output to reference `dokploy-ctl` commands:
```
Created compose app: IWcYWttLzI
Fixed sourceType to 'raw'

Next steps:
  dokploy-ctl deploy IWcYWttLzI docker-compose.prod.yml --env
  dokploy-ctl status IWcYWttLzI
```

### `api` — unchanged

Raw API passthrough stays as escape hatch. No changes needed.

### `login` — unchanged

### Bare `dokploy-ctl` (no args, no `--help`)

Instead of showing usage/help text, lists all compose apps (same as `dokploy-ctl find`). `--help` still shows help text as usual.

---

## Removed

- `--live` flag on `status` (always shows live containers)

**`sync` is kept.** It updates compose file + env in Dokploy without deploying. Same `--env` / `--env-file` flag pattern as `deploy`.

```
dokploy-ctl sync <compose-id> <compose-file> [--env] [--env-file FILE]
```

```
[00:00] Syncing compose file (2,847 chars)...
[00:01] Synced. 2,847 chars persisted, sourceType=raw.
[00:01] Done (1s total).
```

With `--env`:
```
[00:00] Resolving env: 5 vars from compose (IMAGE_TAG, DB_PASSWORD, ...)
[00:00] Syncing compose file (2,847 chars) + env (5 vars)...
[00:01] Synced. 2,847 chars persisted, 5 env vars persisted.
[00:01] Done (1s total).
```

---

## API Endpoints Reference

| Command | Dokploy API endpoints used |
|---|---|
| `deploy` | `compose.update`, `deployment.allByCompose`, `compose.deploy`, `compose.one`, `docker.getContainers` + WebSocket (deploy log, container logs) |
| `sync` | `compose.update` |
| `status` | `compose.one`, `docker.getContainers` |
| `find` | `project.all` (returns all projects with nested compose apps) |
| `stop` | `compose.stop` |
| `start` | `compose.start`, `compose.one`, `docker.getContainers` |
| `logs` | `compose.one`, `docker.getContainers` + WebSocket (container logs or deploy log) |
| `init` | `compose.create`, `compose.update` |
| `api` | any (passthrough) |

Note: `docker.getContainers` returns `name`, `state`, `status`, `containerId`, `image`, `ports`. The `status` field contains uptime info (e.g., "Up 2 hours (healthy)"). Image and uptime are available from this endpoint.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success — all operations completed, containers healthy |
| 1 | Failure — deploy failed, containers unhealthy, timeout, API error, missing config |

All commands use the same two exit codes. CI and agents rely on exit code to determine success/failure.

## Polling

Deploy and health-check polling use 5-second intervals. Default deploy timeout: 300s (60 polls). Default health timeout: 120s (24 polls). Both configurable via `--timeout`.

---

## Architecture Changes

### Timestamp utility

Shared timer class used by all commands:

```python
class Timer:
    def __init__(self): self.start = time.monotonic()
    def stamp(self) -> str:
        elapsed = time.monotonic() - self.start
        mins, secs = divmod(int(elapsed), 60)
        return f"[{mins:02d}:{secs:02d}]"
```

### Hint system

A `hints` module that maps known error patterns to actionable suggestions:

```python
def hint_unhealthy(compose_id: str, service: str) -> str:
    return (
        f"Hint: {service} is unhealthy.\n"
        f"  dokploy-ctl logs {compose_id} --service {service} --since 5m"
    )
```

Hints are deterministic — pattern-matched from container state, deploy errors, API responses. Not AI-generated.

### Output formatting

All commands use a shared output module that handles:
- Timestamped lines via `Timer`
- Service/container reference formatting (service name + container ID)
- Hint emission
- Summary line with total duration

---

## Migration / Breaking Changes

1. **`deploy` no longer resolves env by default.** Existing CI pipelines that rely on auto env resolution must add `--env` flag. This is the only breaking change.
2. **`status` always shows live containers.** `--live` flag is removed (ignored if passed for backward compat, with deprecation warning).
3. **`logs --since` default changes** from `all` to `5m`.
4. **Bare `dokploy-ctl`** shows compose apps instead of help text.

---

## Out of Scope (v2)

- Docker Swarm support
- Python SDK as importable library (defer — if CLI output is rich enough, library imports become unnecessary)
- `--json` / `--toon` output format flags (plain text is sufficient for AI agents)
- MCP server integration
- Compose linting (handled by ai-harness)
