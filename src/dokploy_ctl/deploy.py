"""Deploy and sync commands."""

import os
import re
import sys
import time
from pathlib import Path

import click

from dokploy_ctl.client import DOKPLOY_ID, DashSafeCommand, api_call, load_config, make_client, print_response
from dokploy_ctl.containers import show_deploy_log, show_problem_logs
from dokploy_ctl.dokploy import DokployClient
from dokploy_ctl.env import resolve_env
from dokploy_ctl.hints import hint_deploy_failed
from dokploy_ctl.polling import check_stall, detect_phase, detect_transitions
from dokploy_ctl.timer import Timer

POLL_INTERVAL = 6
HEARTBEAT_INTERVAL = 30
STALL_THRESHOLD = 90
DEPLOY_DONE_GRACE = 30


def _auto_diagnose(
    timer: Timer,
    url: str,
    token: str,
    compose_id: str,
    app_name: str,
    current_containers: list,
    latest_dep,
    transition_history: list[tuple[str, list[str]]],
    reason: str,
) -> None:
    """Fetch logs for problem containers and exit. Called on stall or deploy-done timeout."""
    timer.log(f"Auto-diagnosing: {reason}")

    if transition_history:
        timer.log("")
        timer.log("Container transitions:")
        for stamp, tlist in transition_history:
            for t in tlist:
                timer.log(f"  {stamp} {t}")
        timer.log("")

    # Auto-fetch deploy log
    log_path = latest_dep.log_path if latest_dep else ""
    if log_path:
        timer.log("=== Deploy build log ===")
        show_deploy_log(url, token, log_path)
        timer.log("")

    # Auto-fetch container logs for problem containers
    unhealthy_count = 0
    if current_containers:
        raw_containers = [
            {"name": f"{app_name}-{c.service}-1", "state": c.state, "status": c.raw_status, "containerId": c.container_id}
            for c in current_containers
        ]
        show_problem_logs(url, token, raw_containers, app_name)
        for c in current_containers:
            if c.state in ("exited", "dead") and "Exited (0)" not in c.raw_status:
                reason_detail = "exited"
                m = re.search(r"Exited \((\d+)\)", c.raw_status)
                if m:
                    reason_detail = f"exited({m.group(1)})"
                timer.log("")
                timer.log(hint_deploy_failed(compose_id, c.service, reason_detail))
                unhealthy_count += 1

    if unhealthy_count == 1:
        timer.summary(f"Deploy failed. {unhealthy_count} unhealthy service.")
    elif unhealthy_count > 1:
        timer.summary(f"Deploy failed. {unhealthy_count} unhealthy services.")
    else:
        timer.summary(f"Deploy failed ({reason}).")
    sys.exit(1)


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


@click.command(cls=DashSafeCommand)
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


@click.command(cls=DashSafeCommand)
@click.argument("compose_id", type=DOKPLOY_ID)
@click.argument("compose_file")
@click.option("--env-file", "-e", default=None, help="Path to .env file")
@click.option("--env", "env_flag", is_flag=True, default=False, help="Resolve ${VAR} refs from environment")
@click.option("--timeout", "-t", default=600, help="Deploy timeout in seconds (default: 600)")
def deploy(compose_id: str, compose_file: str, env_file: str | None, env_flag: bool, timeout: int) -> None:
    """Sync + deploy + poll container transitions + verify health."""
    dk = DokployClient()
    url, token = dk.url, dk.token
    timer = Timer()

    # Step 1: sync compose file
    compose_content = Path(compose_file).read_text()
    compose_len = len(compose_content)
    timer.log(f"Syncing compose file ({compose_len:,} chars)...")

    env_content = resolve_env(env_flag, env_file, compose_content)
    updated = dk.update_compose(compose_id, compose_content, env_content)
    stored_len = len(updated.compose_file)

    if stored_len < 10:
        timer.log(f"error: compose.update did not persist composeFile (got {stored_len} chars, sent {compose_len})")
        sys.exit(1)

    timer.log(f"Synced. {stored_len:,} chars persisted.")
    if env_content is not None:
        timer.log(f"Env: {len(updated.env):,} chars persisted.")

    # Step 2: get app_name and pre-deploy container snapshot
    compose_app = dk.get_compose(compose_id)
    app_name = compose_app.app_name

    pre_containers = dk.get_containers(app_name)
    pre_deploy_ids: set[str] = {c.container_id for c in pre_containers}
    pre_names = ", ".join(c.service for c in pre_containers) if pre_containers else "none"

    # Step 3: snapshot previous deployment ID
    prev_dep = dk.get_latest_deployment(compose_id)
    prev_deploy_id = prev_dep.deployment_id if prev_dep else None

    # Step 4: trigger deploy
    image_tag = os.environ.get("IMAGE_TAG", "")
    title = f"Deploy {image_tag}" if image_tag else "Deploy via dokploy-ctl"

    timer.log(f"Triggering deploy ({title})...")
    dk.trigger_deploy(compose_id, title)

    timer.log(f"Snapshot: {len(pre_containers)} containers ({pre_names})")

    # Step 5: smart poll loop — event-driven transitions
    prev_containers = list(pre_containers)
    prev_phase = ""
    last_transition_time = timer.elapsed()
    last_heartbeat_time = timer.elapsed()
    last_stall_warning_time: float | None = None
    deploy_done_time: float | None = None
    transition_history: list[tuple[str, list[str]]] = []
    deploy_status = "running"

    max_cycles = timeout // POLL_INTERVAL
    for _ in range(1, max_cycles + 1):
        time.sleep(POLL_INTERVAL)

        # Get current state
        latest_dep = dk.get_latest_deployment(compose_id)
        current_containers = dk.get_containers(app_name)
        now = timer.elapsed()

        # Skip if still waiting for new deployment to appear
        if latest_dep and prev_deploy_id and latest_dep.deployment_id == prev_deploy_id:
            if now - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                timer.log("(waiting for new deployment to appear...)")
                last_heartbeat_time = now
            continue

        deploy_status = latest_dep.status if latest_dep else "unknown"

        # Detect container transitions
        transitions = detect_transitions(prev_containers, current_containers)
        phase = detect_phase(pre_deploy_ids, current_containers)

        if transitions:
            last_transition_time = now
            last_heartbeat_time = now
            last_stall_warning_time = None
            stamp = timer.stamp()
            for t in transitions:
                transition_history.append((stamp, [t]))
                timer.log(t)

        # Emit phase change
        if phase != prev_phase:
            if phase == "healthy":
                healthy_count = len(current_containers)
                timer.log(f"Phase: healthy. All {healthy_count} containers up.")
            elif phase != "unknown" or prev_phase:
                timer.log(f"deploy={deploy_status} | Phase: {phase}")
            prev_phase = phase

        # Heartbeat if no recent output
        if now - last_heartbeat_time >= HEARTBEAT_INTERVAL:
            stalled = check_stall(last_transition_time, now, STALL_THRESHOLD)
            if stalled and deploy_status == "done":
                # Deploy finished but containers aren't healthy — auto-diagnose
                _auto_diagnose(
                    timer,
                    url,
                    token,
                    compose_id,
                    app_name,
                    current_containers,
                    latest_dep,
                    transition_history,
                    reason=f"deploy done but containers not healthy after {STALL_THRESHOLD}s",
                )
            elif stalled:
                if last_stall_warning_time is None:
                    timer.log(f"WARNING: no container changes for {STALL_THRESHOLD}s. Deploy may be stalled.")
                    timer.log(f"  Hint: dokploy-ctl logs {compose_id} -D    (check deploy build log)")
                    last_stall_warning_time = now
                else:
                    timer.log(f"(no changes for {HEARTBEAT_INTERVAL}s — still stalled)")
            else:
                timer.log(f"(no changes for {HEARTBEAT_INTERVAL}s — still in {phase})")
            last_heartbeat_time = now

        # Error path
        if deploy_status == "error":
            error_msg = latest_dep.error_message if latest_dep else "unknown error"
            timer.log(f'deploy=error | Deploy failed: "{error_msg}"')
            _auto_diagnose(
                timer,
                url,
                token,
                compose_id,
                app_name,
                current_containers,
                latest_dep,
                transition_history,
                reason="deploy error",
            )

        # Success path: healthy phase AND deploy done
        if phase == "healthy" and deploy_status == "done":
            timer.summary("All containers healthy. Deploy succeeded.")
            return

        # Also accept: deploy done even if phase detection is uncertain (no containers = no health check)
        if deploy_status == "done" and not current_containers:
            timer.summary("Deploy succeeded.")
            return

        # Track when deploy first became done (for grace period)
        if deploy_status == "done" and deploy_done_time is None:
            deploy_done_time = now

        # Grace period: deploy done but not healthy — give containers time to start
        if deploy_done_time is not None and (now - deploy_done_time) > DEPLOY_DONE_GRACE:
            _auto_diagnose(
                timer,
                url,
                token,
                compose_id,
                app_name,
                current_containers,
                latest_dep,
                transition_history,
                reason=f"deploy done but containers not healthy after {DEPLOY_DONE_GRACE}s grace period",
            )

        prev_containers = current_containers

    # Timeout
    timer.log(f"Deploy timed out after {timeout}s")
    timer.summary("Deploy failed.")
    sys.exit(1)
