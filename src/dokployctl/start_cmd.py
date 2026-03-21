"""Start command."""

import click

from dokployctl.client import DOKPLOY_ID, _err, api_call, load_config, make_client
from dokployctl.containers import get_containers, verify_container_health
from dokployctl.hints import hint_unhealthy
from dokployctl.output import parse_service_name
from dokployctl.timer import Timer


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
def start(compose_id: str) -> None:
    """Start a stopped compose app and verify health."""
    timer = Timer()
    url, token = load_config()
    client = make_client(url, token)

    timer.log(f"Starting compose {compose_id}...")
    resp = api_call(client, "POST", "compose.start", {"composeId": compose_id})
    if resp.is_error:
        _err(f"error: compose.start failed (HTTP {resp.status_code})")
        raise SystemExit(1)

    # Get app name for health check
    app_resp = api_call(client, "GET", "compose.one", {"composeId": compose_id})
    if app_resp.is_error:
        _err("warning: could not fetch app info for health check")
        timer.summary("Started (health check skipped).")
        return

    app_name = app_resp.json().get("appName", "")
    if not app_name:
        timer.summary("Started (no appName for health check).")
        return

    timer.log("Verifying container health...")
    healthy = verify_container_health(client, app_name, timeout=120)
    if healthy:
        timer.summary("All containers healthy. Started.")
    else:
        containers = get_containers(client, app_name)
        for c in containers:
            state = c.get("state", "")
            status = c.get("status", "")
            if state != "running" or "(unhealthy)" in status:
                svc = parse_service_name(c.get("name", ""), app_name)
                click.echo(hint_unhealthy(compose_id, svc))
        timer.summary("Started but not all containers healthy.")
        raise SystemExit(1)
