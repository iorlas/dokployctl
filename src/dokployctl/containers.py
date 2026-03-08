"""Container health checking and status helpers."""

import time

import click
import httpx

from dokployctl.client import _err, api_call
from dokployctl.websocket import fetch_container_logs, fetch_deploy_log


def get_containers(client: httpx.Client, app_name: str) -> list[dict]:
    resp = api_call(client, "GET", "docker.getContainers")
    if resp.is_error:
        return []
    containers = resp.json()
    if not isinstance(containers, list):
        return []
    return [c for c in containers if app_name in c.get("name", "")]


def _is_one_shot(c: dict) -> bool:
    """Exited with code 0 = successful migration/init task."""
    return c.get("state") == "exited" and "Exited (0)" in c.get("status", "")


def _container_ok(c: dict) -> bool:
    if _is_one_shot(c):
        return True
    state = c.get("state", "")
    status = c.get("status", "")
    if state == "running" and "(healthy)" in status:
        return True
    return state == "running" and "(health:" not in status.lower() and "(unhealthy)" not in status.lower()


def _container_converging(c: dict) -> bool:
    state = c.get("state", "")
    status = c.get("status", "")
    if state == "running" and "(health: starting)" in status.lower():
        return True
    return state == "restarting"


def _container_label(c: dict, app_name: str) -> str:
    name = c.get("name", "?").replace(f"{app_name}-", "").rstrip("-1234567890")
    status = c.get("status", "")
    state = c.get("state", "?")
    if _is_one_shot(c):
        return ""  # skip in output
    if "(healthy)" in status:
        return f"{name}=ok"
    if "(health: starting)" in status.lower():
        return f"{name}=starting"
    if state == "restarting":
        return f"{name}=restarting"
    return f"{name}={state}"


def show_problem_logs(base_url: str, token: str, containers: list[dict], app_name: str) -> None:
    problem = [
        c
        for c in sorted(
            containers,
            key=lambda c: 0 if c.get("state") in ("exited", "dead", "created") else 1 if "(unhealthy)" in c.get("status", "") else 2,
        )
        if not _container_ok(c) and not _is_one_shot(c)
    ]

    if not problem:
        return

    _err("\nLogs for problem containers:")
    for c in problem:
        cid = c.get("containerId", "")
        if not cid:
            continue
        short = c.get("name", "?").replace(f"{app_name}-", "").rstrip("-1234567890")
        _err(f"\n--- {short} ({c.get('state', '?')}, {c.get('status', '')}) ---")
        for line in fetch_container_logs(base_url, token, cid, tail=50, since="5m", recv_timeout=3):
            _err(f"  {line.rstrip()[:200]}")


def show_deploy_log(base_url: str, token: str, log_path: str) -> None:
    if not log_path:
        return
    _err("\nDeploy build log:")
    lines = fetch_deploy_log(base_url, token, log_path, recv_timeout=5)
    if not lines:
        _err("  (no log content — file may have been cleaned up)")
        return
    for line in lines:
        _err(f"  {line.rstrip()[:200]}")


def verify_container_health(client: httpx.Client, app_name: str, timeout: int = 120) -> bool:
    max_attempts = timeout // 5
    for i in range(1, max_attempts + 1):
        containers = get_containers(client, app_name)
        if not containers:
            click.echo(f"  [health {i}/{max_attempts}] No containers found for {app_name}")
            time.sleep(5)
            continue

        all_ok = all(_container_ok(c) for c in containers)
        still_converging = any(_container_converging(c) for c in containers)

        parts = [_container_label(c, app_name) for c in containers]
        parts = [p for p in parts if p]  # filter out one-shot empties
        click.echo(f"  [health {i}/{max_attempts}] {', '.join(parts)}")

        if all_ok and containers:
            return True
        if not still_converging:
            return False

        time.sleep(5)

    return False
