"""Deploy and sync commands."""

import os
import re
import sys
import time
from pathlib import Path

import click

from dokploy_ctl.client import DOKPLOY_ID, api_call, load_config, make_client, print_response
from dokploy_ctl.containers import get_containers, show_deploy_log, show_problem_logs, verify_container_health
from dokploy_ctl.env import resolve_env
from dokploy_ctl.hints import hint_deploy_failed, hint_unhealthy
from dokploy_ctl.output import parse_service_name
from dokploy_ctl.timer import Timer


def _do_sync(client, compose_id: str, compose_file: str, env_file: str | None, env_flag: bool = False, timer: Timer | None = None) -> None:
    """Shared sync logic used by both sync and deploy commands."""
    if timer is None:
        timer = Timer()

    compose_content = Path(compose_file).read_text()
    compose_len = len(compose_content)

    timer.log(f"Syncing compose file ({compose_len:,} chars)...")

    payload: dict = {
        "composeId": compose_id,
        "composeFile": compose_content,
        "sourceType": "raw",
        "composePath": "./docker-compose.yml",
    }

    env_content = resolve_env(env_flag, env_file, compose_content)
    if env_content is not None:
        payload["env"] = env_content

    resp = api_call(client, "POST", "compose.update", payload)
    if resp.is_error:
        print_response(resp)
        sys.exit(1)

    result = resp.json()
    stored_len = len(result.get("composeFile", ""))

    if stored_len < 10:
        timer.log(f"error: compose.update did not persist composeFile (got {stored_len} chars, sent {compose_len})")
        sys.exit(1)

    source_type = result.get("sourceType", "?")
    timer.log(f"Synced. {stored_len:,} chars persisted, sourceType={source_type}.")

    if env_content is not None:
        timer.log(f"Env: {len(result.get('env', '')):,} chars persisted.")


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
@click.argument("compose_file")
@click.option("--env-file", "-e", default=None, help="Path to .env file")
@click.option("--env", "env_flag", is_flag=True, default=False, help="Resolve ${VAR} refs from environment")
def sync(compose_id: str, compose_file: str, env_file: str | None, env_flag: bool) -> None:
    """Sync compose file + env to Dokploy."""
    url, token = load_config()
    client = make_client(url, token)
    timer = Timer()
    _do_sync(client, compose_id, compose_file, env_file, env_flag, timer)


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
@click.argument("compose_file")
@click.option("--env-file", "-e", default=None, help="Path to .env file")
@click.option("--env", "env_flag", is_flag=True, default=False, help="Resolve ${VAR} refs from environment")
@click.option("--timeout", "-t", default=300, help="Deploy timeout in seconds (default: 300)")
def deploy(compose_id: str, compose_file: str, env_file: str | None, env_flag: bool, timeout: int) -> None:
    """Sync + deploy + poll + verify container health."""
    url, token = load_config()
    client = make_client(url, token)
    timer = Timer()

    # Step 1: sync
    _do_sync(client, compose_id, compose_file, env_file, env_flag, timer)

    # Step 2: snapshot previous deployment ID
    pre_resp = api_call(client, "GET", "deployment.allByCompose", {"composeId": compose_id})
    prev_deploy_id = None
    if not pre_resp.is_error:
        pre_deps = pre_resp.json()
        if pre_deps and isinstance(pre_deps, list):
            prev_deploy_id = pre_deps[0].get("deploymentId")

    # Step 3: trigger deploy
    image_tag = os.environ.get("IMAGE_TAG", "")
    title = f"Deploy {image_tag}" if image_tag else "Deploy via dokploy-ctl"

    timer.log(f"Triggering deploy ({title})...")
    deploy_resp = api_call(
        client,
        "POST",
        "compose.deploy",
        {
            "composeId": compose_id,
            "title": title,
        },
    )
    if deploy_resp.is_error:
        print_response(deploy_resp)
        timer.summary("Deploy failed.")
        sys.exit(1)

    # Step 4: poll for NEW deployment
    max_attempts = timeout // 5
    for i in range(1, max_attempts + 1):
        time.sleep(5)
        status_resp = api_call(client, "GET", "deployment.allByCompose", {"composeId": compose_id})
        if status_resp.is_error:
            status_resp = api_call(client, "GET", "deployment.all", {"composeId": compose_id})

        if status_resp.is_error:
            timer.log(f"Polling... [{i}/{max_attempts}] Failed to fetch status (HTTP {status_resp.status_code})")
            continue

        deployments = status_resp.json()
        if not deployments:
            timer.log(f"Polling... [{i}/{max_attempts}] No deployments found")
            continue

        latest = deployments[0] if isinstance(deployments, list) else deployments

        if prev_deploy_id and latest.get("deploymentId") == prev_deploy_id:
            timer.log(f"Polling... [{i}/{max_attempts}] Waiting for new deployment...")
            continue

        dep_status = latest.get("status", "unknown")
        timer.log(f"Polling... [{i}/{max_attempts}] status={dep_status}")

        if dep_status == "done":
            timer.log("Dokploy reports deploy done.")
            break

        if dep_status == "error":
            error_msg = latest.get("errorMessage", "unknown error")
            timer.log(f'Deploy failed: "{error_msg}"')
            timer.log("")

            # Auto-fetch deploy log
            log_path = latest.get("logPath", "")
            if log_path:
                timer.log("=== Deploy build log ===")
                show_deploy_log(url, token, log_path)
                timer.log("")

            # Auto-fetch container logs for problem containers
            app_resp = api_call(client, "GET", "compose.one", {"composeId": compose_id})
            unhealthy_count = 0
            if not app_resp.is_error:
                app_name = app_resp.json().get("appName", "")
                containers = get_containers(client, app_name)
                if containers:
                    show_problem_logs(url, token, containers, app_name)
                    # Emit hints for each failed container
                    for c in containers:
                        state = c.get("state", "")
                        status = c.get("status", "")
                        if state in ("exited", "dead") and "Exited (0)" not in status:
                            service = parse_service_name(c.get("name", "?"), app_name)
                            # Parse exit code from status like "Exited (1) 30s ago"
                            reason = "exited"
                            m = re.search(r"Exited \((\d+)\)", status)
                            if m:
                                reason = f"exited({m.group(1)})"
                            timer.log("")
                            timer.log(hint_deploy_failed(compose_id, service, reason))
                            unhealthy_count += 1

            if unhealthy_count == 1:
                timer.summary(f"Deploy failed. {unhealthy_count} unhealthy service.")
            elif unhealthy_count > 1:
                timer.summary(f"Deploy failed. {unhealthy_count} unhealthy services.")
            else:
                timer.summary("Deploy failed.")
            sys.exit(1)
    else:
        timer.log(f"Deploy timed out after {timeout}s")
        timer.summary("Deploy failed.")
        sys.exit(1)

    # Step 5: verify container health
    timer.log("Verifying container health...")
    app_resp = api_call(client, "GET", "compose.one", {"composeId": compose_id})
    if app_resp.is_error:
        timer.log("warning: could not fetch app info for health check")
        timer.summary("Deploy failed.")
        sys.exit(1)

    app_name = app_resp.json().get("appName", "")
    if not app_name:
        timer.log("warning: no appName found, skipping health check")
        timer.summary("Deploy succeeded.")
        return

    healthy = verify_container_health(client, app_name, timeout=120)
    if healthy:
        timer.summary("All containers healthy. Deploy succeeded.")
    else:
        timer.log("warning: Deploy done but not all containers healthy.")
        containers = get_containers(client, app_name)
        show_problem_logs(url, token, containers, app_name)

        # Emit hints for unhealthy containers
        unhealthy_count = 0
        for c in containers:
            state = c.get("state", "")
            status = c.get("status", "")
            if not _container_ok_simple(state, status):
                service = parse_service_name(c.get("name", "?"), app_name)
                timer.log(hint_unhealthy(compose_id, service))
                unhealthy_count += 1

        if unhealthy_count == 1:
            timer.summary(f"Deploy failed. {unhealthy_count} unhealthy service.")
        elif unhealthy_count > 1:
            timer.summary(f"Deploy failed. {unhealthy_count} unhealthy services.")
        else:
            timer.summary("Deploy failed.")
        sys.exit(1)


def _container_ok_simple(state: str, status: str) -> bool:
    """Simple health check without importing containers module internals."""
    return (
        (state == "exited" and "Exited (0)" in status)
        or (state == "running" and "(healthy)" in status)
        or (state == "running" and "(health:" not in status.lower() and "(unhealthy)" not in status.lower())
    )
