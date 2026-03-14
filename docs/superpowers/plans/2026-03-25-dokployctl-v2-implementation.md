# dokployctl v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform dokployctl into an AI-native CLI with LDD output, auto-escalation on failure, deterministic hints, and new discovery/lifecycle commands.

**Architecture:** Infrastructure modules first (timer, output, hints), then modify existing commands to use them, then add new commands (find, stop, start). Each task produces working, testable code. The env resolution change (`--env` opt-in) is applied to deploy and sync together.

**Tech Stack:** Python 3.12+, click, httpx, websockets, pytest, ruff

**Spec:** `docs/superpowers/specs/2026-03-25-dokployctl-v2-ai-native-design.md`

---

## File Structure

```
src/dokployctl/
├── __init__.py         # Version bump 0.1.0 → 0.2.0
├── cli.py              # MODIFY: add find/stop/start, bare invocation → find
├── client.py           # UNCHANGED
├── timer.py            # NEW: Timer class for timestamped output
├── output.py           # NEW: Shared output formatting (stamp, hint, summary)
├── hints.py            # NEW: Deterministic hint patterns
├── deploy.py           # MODIFY: --env flag, LDD output, auto-escalation
├── status.py           # MODIFY: merge --live, rich container table, hints
├── logs.py             # MODIFY: --since default 5m, timestamps, container IDs
├── init_cmd.py         # MODIFY: updated next-steps output
├── find_cmd.py         # NEW: find/list compose apps
├── stop_cmd.py         # NEW: stop compose app
├── start_cmd.py        # NEW: start compose app + health check
├── containers.py       # MODIFY: minor — use output module for formatting
├── env.py              # MODIFY: resolve_env conditional on --env flag
├── websocket.py        # UNCHANGED
├── api_cmd.py          # UNCHANGED
tests/
├── test_timer.py       # NEW
├── test_output.py      # NEW
├── test_hints.py       # NEW
├── test_find.py        # NEW
├── test_stop_start.py  # NEW
├── test_deploy_v2.py   # NEW: deploy --env flag behavior
├── test_env_v2.py      # NEW: env resolution opt-in
├── test_status_v2.py   # NEW: merged status output
```

---

### Task 1: Timer module

**Files:**
- Create: `src/dokployctl/timer.py`
- Create: `tests/test_timer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_timer.py
import time
from dokployctl.timer import Timer

def test_timer_starts_at_zero():
    t = Timer()
    assert t.stamp() == "[00:00]"

def test_timer_advances():
    t = Timer()
    t._start -= 65  # simulate 1m5s elapsed
    assert t.stamp() == "[01:05]"

def test_timer_stamp_message():
    t = Timer()
    assert t.log("Syncing...") == "[00:00] Syncing..."
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd /Users/iorlas/Workspaces/dokployctl && uv run pytest tests/test_timer.py -v`

- [ ] **Step 3: Implement timer.py**

```python
"""Shared timer for timestamped CLI output."""

import time
import click


class Timer:
    def __init__(self) -> None:
        self._start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def stamp(self) -> str:
        mins, secs = divmod(int(self.elapsed()), 60)
        return f"[{mins:02d}:{secs:02d}]"

    def log(self, msg: str) -> str:
        line = f"{self.stamp()} {msg}"
        click.echo(line)
        return line

    def summary(self, msg: str) -> str:
        total = int(self.elapsed())
        line = f"{self.stamp()} {msg} ({total}s total)"
        click.echo(line)
        return line
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Run lint:** `uv run ruff check src/dokployctl/timer.py tests/test_timer.py`
- [ ] **Step 6: Commit**

```bash
git add src/dokployctl/timer.py tests/test_timer.py
git commit -m "feat: timer module — timestamped output for LDD"
```

---

### Task 2: Hints module

**Files:**
- Create: `src/dokployctl/hints.py`
- Create: `tests/test_hints.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hints.py
from dokployctl.hints import hint_unhealthy, hint_deploy_failed, hint_restart

def test_hint_unhealthy_includes_compose_id():
    h = hint_unhealthy("IWcY", "worker")
    assert "IWcY" in h
    assert "worker" in h
    assert "dokployctl logs" in h

def test_hint_deploy_failed_includes_log_command():
    h = hint_deploy_failed("IWcY", "worker", "exited(1)")
    assert "dokployctl logs IWcY --service worker" in h

def test_hint_restart():
    h = hint_restart("IWcY")
    assert "dokployctl start IWcY" in h
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement hints.py**

```python
"""Deterministic hints — map error patterns to actionable suggestions."""


def hint_unhealthy(compose_id: str, service: str) -> str:
    return (
        f"Hint: {service} is unhealthy.\n"
        f"  dokployctl logs {compose_id} --service {service} --since 5m"
    )


def hint_deploy_failed(compose_id: str, service: str, reason: str) -> str:
    return (
        f"Hint: {service} failed ({reason}). Check the Dockerfile entrypoint or config.\n"
        f"  dokployctl logs {compose_id} --service {service} --tail 200\n"
        f"  dokployctl status {compose_id}"
    )


def hint_restart(compose_id: str) -> str:
    return f"Hint: To restart: dokployctl start {compose_id}"


def hint_stopped(compose_id: str) -> str:
    return f"Hint: To start: dokployctl start {compose_id}"


def hint_no_containers(compose_id: str) -> str:
    return (
        f"Hint: No containers found. The app may be stopped.\n"
        f"  dokployctl start {compose_id}"
    )
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/dokployctl/hints.py tests/test_hints.py
git commit -m "feat: hints module — deterministic actionable suggestions"
```

---

### Task 3: Output formatting module

**Files:**
- Create: `src/dokployctl/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_output.py
from dokployctl.output import format_container_row, format_container_table

def test_format_container_row():
    c = {"name": "app-worker-1", "state": "running", "status": "Up 2h (healthy)", "containerId": "abc123", "image": "ghcr.io/iorlas/app:main-abc"}
    row = format_container_row(c, "app")
    assert "worker" in row
    assert "running" in row
    assert "healthy" in row
    assert "abc123" in row

def test_format_container_table_headers():
    containers = [
        {"name": "app-worker-1", "state": "running", "status": "Up 2h (healthy)", "containerId": "abc123", "image": "img:tag"},
    ]
    table = format_container_table(containers, "app")
    assert "SERVICE" in table
    assert "STATE" in table
    assert "CONTAINER ID" in table
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement output.py**

Formatting helpers for container tables, service references, and summary lines. Extract service name from container name by stripping the app_name prefix and trailing instance numbers. Parse health/uptime from the Docker status string.

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/dokployctl/output.py tests/test_output.py
git commit -m "feat: output module — container table formatting"
```

---

### Task 4: Env resolution opt-in (`--env` flag)

**Files:**
- Modify: `src/dokployctl/env.py`
- Modify: `src/dokployctl/deploy.py`
- Create: `tests/test_env_v2.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_env_v2.py
from dokployctl.env import resolve_env

def test_resolve_env_returns_none_when_no_flag(monkeypatch):
    """Default: no env resolution even if compose has ${VAR} refs."""
    result = resolve_env(env_flag=False, env_file=None, compose_content="image: ${TAG}")
    assert result is None

def test_resolve_env_resolves_when_flag_set(monkeypatch):
    monkeypatch.setenv("TAG", "v1")
    result = resolve_env(env_flag=True, env_file=None, compose_content="image: ${TAG}")
    assert "TAG=v1" in result

def test_resolve_env_errors_on_both_flags():
    import pytest
    with pytest.raises(SystemExit):
        resolve_env(env_flag=True, env_file="some.env", compose_content="")
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Update `env.py`**

Change `resolve_env` signature to accept `env_flag: bool` parameter. When `env_flag=False` and `env_file=None`, return `None` (no env resolution). When both `env_flag=True` and `env_file` is set, exit with error (mutually exclusive).

```python
def resolve_env(env_flag: bool, env_file: str | None, compose_content: str) -> str | None:
    if env_flag and env_file:
        click.echo("error: --env and --env-file are mutually exclusive", err=True)
        sys.exit(1)
    if env_file:
        return Path(env_file).read_text()
    if env_flag:
        env_vars = extract_env_vars(compose_content)
        if env_vars:
            return build_env_from_compose(compose_content)
    return None
```

- [ ] **Step 4: Update `deploy.py`**

Add `--env` flag to both `deploy` and `sync` commands. Update `_do_sync` to pass `env_flag` through to `resolve_env`. Update deploy title from "dokctl" to "dokployctl".

- [ ] **Step 5: Run tests, verify pass** (both new and existing)

Run: `uv run pytest -v`

- [ ] **Step 6: Commit**

```bash
git add src/dokployctl/env.py src/dokployctl/deploy.py tests/test_env_v2.py
git commit -m "feat: env resolution opt-in — --env flag, breaking change"
```

---

### Task 5: Deploy with LDD output + auto-escalation

**Files:**
- Modify: `src/dokployctl/deploy.py`
- Create: `tests/test_deploy_v2.py`

- [ ] **Step 1: Write failing tests for LDD output**

Test that deploy output includes timestamps and the timer summary line. Use click's `CliRunner` to capture output. Mock the API calls.

```python
# tests/test_deploy_v2.py
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from dokployctl.cli import cli

def test_deploy_output_has_timestamps():
    """Deploy output should include [MM:SS] timestamps."""
    # ... mock api_call, invoke deploy, check output contains "[00:00]"

def test_deploy_failure_shows_logs_automatically():
    """On deploy failure, auto-fetch and display build + container logs."""
    # ... mock deploy returning error status, verify log output appears
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Rewrite deploy command**

Replace all `click.echo()` calls with `timer.log()`. Add auto-escalation block after deploy failure: fetch deploy build log, fetch container logs for problem services, emit hints. Use `Timer` from task 1, hints from task 2.

Key changes to `deploy()` function:
1. Create `Timer()` at start
2. Replace `click.echo(f"...")` → `timer.log(f"...")`
3. After poll loop, on error: call `show_deploy_log` and `show_problem_logs` automatically (currently only done inside the error branch — ensure it also happens on health check failure)
4. Emit hints via `hints.hint_deploy_failed()` for each unhealthy service
5. Final line: `timer.summary("Deploy succeeded.")` or `timer.summary("Deploy failed. N unhealthy services.")`

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`

- [ ] **Step 5: Commit**

```bash
git add src/dokployctl/deploy.py tests/test_deploy_v2.py
git commit -m "feat: deploy with LDD output — timestamps, auto-escalation, hints"
```

---

### Task 6: Status — merge live containers, rich output

**Files:**
- Modify: `src/dokployctl/status.py`
- Create: `tests/test_status_v2.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_status_v2.py
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from dokployctl.cli import cli

def test_status_shows_containers_by_default():
    """status should always show containers (no --live needed)."""
    # Mock compose.one and docker.getContainers
    # Verify output contains "Containers:" section

def test_status_shows_hint_for_unhealthy():
    """Unhealthy containers should trigger a hint."""
    # Mock container with state=running, status containing "(unhealthy)"
    # Verify output contains "Hint:"
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Rewrite status command**

Remove `--live` flag (accept but ignore with deprecation warning for backward compat). Always fetch containers. Use `output.format_container_table()` for container display. Add `Timer` timestamps. Emit hints for unhealthy services. Show IMAGE and UPTIME columns (parsed from `docker.getContainers` response).

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/dokployctl/status.py tests/test_status_v2.py
git commit -m "feat: status merged — always shows live containers, hints, timestamps"
```

---

### Task 7: Find command

**Files:**
- Create: `src/dokployctl/find_cmd.py`
- Create: `tests/test_find.py`
- Modify: `src/dokployctl/cli.py` — register find command

- [ ] **Step 1: Write failing tests**

```python
# tests/test_find.py
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from dokployctl.cli import cli

def test_find_lists_all_projects():
    """find with no args lists all projects."""
    # Mock project.all returning projects with compose apps
    # Verify output contains project names and compose IDs

def test_find_filters_by_name():
    """find <name> filters to matching projects."""
    # Mock project.all, invoke with name arg
    # Verify only matching projects shown
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement find_cmd.py**

```python
"""Find command — list/search compose apps."""

import click
from dokployctl.client import load_config, make_client, api_call, _err
from dokployctl.timer import Timer


@click.command()
@click.argument("name", required=False)
def find(name: str | None) -> None:
    """List compose apps. Optionally filter by project name."""
    timer = Timer()
    url, token = load_config()
    client = make_client(url, token)

    timer.log("Searching projects...")
    resp = api_call(client, "GET", "project.all")
    if resp.is_error:
        _err(f"error: failed to list projects (HTTP {resp.status_code})")
        raise SystemExit(1)

    projects = resp.json()
    # project.all returns list of projects, each with nested compose apps
    rows = []
    for proj in projects:
        proj_name = proj.get("name", "?")
        for comp in proj.get("compose", []):
            comp_id = comp.get("composeId", "?")
            app_name = comp.get("appName", "?")
            status = comp.get("composeStatus", "?")
            if name and name.lower() not in proj_name.lower() and name.lower() not in app_name.lower():
                continue
            rows.append((proj_name, comp_id, app_name, status))

    if not rows:
        click.echo("No compose apps found." + (f" (filter: {name})" if name else ""))
        return

    # Print table
    click.echo(f"\n  {'PROJECT':<20} {'COMPOSE ID':<24} {'APP NAME':<45} {'STATUS'}")
    for proj_name, comp_id, app_name, status in rows:
        click.echo(f"  {proj_name:<20} {comp_id:<24} {app_name:<45} {status}")

    timer.summary(f"\n{len(rows)} compose apps found.")
```

- [ ] **Step 4: Register in cli.py**

```python
from dokployctl.find_cmd import find
cli.add_command(find)
```

- [ ] **Step 5: Run tests, verify pass**
- [ ] **Step 6: Commit**

```bash
git add src/dokployctl/find_cmd.py tests/test_find.py src/dokployctl/cli.py
git commit -m "feat: find command — list/search compose apps by project name"
```

---

### Task 8: Stop and Start commands

**Files:**
- Create: `src/dokployctl/stop_cmd.py`
- Create: `src/dokployctl/start_cmd.py`
- Create: `tests/test_stop_start.py`
- Modify: `src/dokployctl/cli.py` — register both commands

- [ ] **Step 1: Write failing tests**

```python
# tests/test_stop_start.py
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from dokployctl.cli import cli

def test_stop_calls_compose_stop():
    """stop should call compose.stop endpoint."""
    # Mock api_call, verify compose.stop called with composeId

def test_start_calls_compose_start():
    """start should call compose.start and verify health."""
    # Mock api_call for compose.start, compose.one, docker.getContainers
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement stop_cmd.py**

```python
"""Stop command."""

import click
from dokployctl.client import load_config, make_client, api_call, _err, DOKPLOY_ID
from dokployctl.hints import hint_restart
from dokployctl.timer import Timer


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
def stop(compose_id: str) -> None:
    """Stop a running compose app."""
    timer = Timer()
    url, token = load_config()
    client = make_client(url, token)

    timer.log(f"Stopping compose {compose_id}...")
    resp = api_call(client, "POST", "compose.stop", {"composeId": compose_id})
    if resp.is_error:
        _err(f"error: compose.stop failed (HTTP {resp.status_code})")
        raise SystemExit(1)

    click.echo(hint_restart(compose_id))
    timer.summary("Stopped.")
```

- [ ] **Step 4: Implement start_cmd.py**

Similar to stop, but after calling `compose.start`, run the same health-check workflow as deploy (poll `docker.getContainers` until healthy, auto-fetch logs on failure). Reuse `verify_container_health` from `containers.py`, but wrap with Timer output.

- [ ] **Step 5: Register both in cli.py**

```python
from dokployctl.stop_cmd import stop
from dokployctl.start_cmd import start
cli.add_command(stop)
cli.add_command(start)
```

- [ ] **Step 6: Run tests, verify pass**
- [ ] **Step 7: Commit**

```bash
git add src/dokployctl/stop_cmd.py src/dokployctl/start_cmd.py tests/test_stop_start.py src/dokployctl/cli.py
git commit -m "feat: stop + start commands with health verification"
```

---

### Task 9: Logs — default --since 5m, timestamps

**Files:**
- Modify: `src/dokployctl/logs.py`

- [ ] **Step 1: Change --since default**

In `logs.py`, change `@click.option("--since", default="all", ...)` to `default="5m"`.

- [ ] **Step 2: Add Timer to logs output**

Wrap the command body with Timer. Add `timer.log(f"Fetching logs for {compose_id} (last {since}, tail {tail})...")` at start. Add `timer.summary("Done.")` at end. Add container ID to service headers: `--- worker (container: abc123) ---`.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`

- [ ] **Step 4: Commit**

```bash
git add src/dokployctl/logs.py
git commit -m "feat: logs — default --since 5m, timestamps, container IDs in headers"
```

---

### Task 10: Init — updated output, bare dokployctl → find

**Files:**
- Modify: `src/dokployctl/init_cmd.py`
- Modify: `src/dokployctl/cli.py`

- [ ] **Step 1: Update init output**

Add Timer. Change final output to suggest dokployctl commands:
```python
click.echo(f"\nNext steps:")
click.echo(f"  dokployctl deploy {compose_id} docker-compose.prod.yml --env")
click.echo(f"  dokployctl status {compose_id}")
```

- [ ] **Step 2: Handle bare `dokployctl` invocation**

In `cli.py`, change the click group to `invoke_without_command=True` and add a callback that runs `find` when no subcommand is given:

```python
@click.group(invoke_without_command=True)
@click.version_option(package_name="dokployctl")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """dokployctl — CLI for Dokploy deployments."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(find)
```

- [ ] **Step 3: Verify bare dokployctl lists apps**

Run: `uv run dokployctl` (without args — should list compose apps, not help)
Run: `uv run dokployctl --help` (should still show help)

- [ ] **Step 4: Run full test suite**

Run: `make check`

- [ ] **Step 5: Commit**

```bash
git add src/dokployctl/init_cmd.py src/dokployctl/cli.py
git commit -m "feat: init updated output, bare dokployctl lists compose apps"
```

---

### Task 11: Version bump + README update

**Files:**
- Modify: `src/dokployctl/__init__.py`
- Modify: `README.md`

- [ ] **Step 1: Bump version to 0.2.0**

```python
__version__ = "0.2.0"
```

- [ ] **Step 2: Update README**

Update command reference table with new commands (find, stop, start). Note breaking changes: `--env` flag required for env resolution in deploy/sync, `--since` default changed to 5m in logs. Add LDD output example.

- [ ] **Step 3: Run full check**

Run: `make check`

- [ ] **Step 4: Test build**

Run: `uv build`

- [ ] **Step 5: Commit and push**

```bash
git add src/dokployctl/__init__.py README.md
git commit -m "feat: v0.2.0 — AI-native CLI with LDD output, new commands"
git push
```
