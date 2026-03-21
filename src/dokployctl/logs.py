"""Logs command."""

import click

from dokployctl.client import DOKPLOY_ID, api_call, load_config, make_client, print_response
from dokployctl.containers import get_containers
from dokployctl.timer import Timer
from dokployctl.websocket import fetch_container_logs, fetch_deploy_log


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
@click.option("--service", "-s", default=None, help="Filter to a specific service name")
@click.option("--tail", "-n", default=100, help="Number of lines (default: 100)")
@click.option("--since", default="5m", help="Time filter: 30s, 5m, 1h, all (default: 5m)")
@click.option("--deploy", "-D", "show_deploy", is_flag=True, help="Show deploy build log instead")
def logs(compose_id: str, service: str | None, tail: int, since: str, show_deploy: bool) -> None:
    """Show container runtime logs (or deploy build log with -D)."""
    timer = Timer()
    timer.log(f"Fetching logs for {compose_id} (last {since}, tail {tail})...")
    url, token = load_config()
    client = make_client(url, token)

    resp = api_call(client, "GET", "compose.one", {"composeId": compose_id})
    if resp.is_error:
        print_response(resp)
        return

    data = resp.json()
    app_name = data.get("appName", "")

    if show_deploy:
        deployments = data.get("deployments", [])
        if not deployments:
            click.echo("No deployments found.")
            return
        latest = deployments[0]
        log_path = latest.get("logPath", "")
        click.echo(f"Deploy: {latest.get('title', '?')} ({latest.get('status', '?')})")
        click.echo(f"  at:   {latest.get('createdAt', '?')}")
        if not log_path:
            click.echo("  (no log path)")
            return
        lines = fetch_deploy_log(url, token, log_path, recv_timeout=5)
        if not lines:
            click.echo("  (no log content — file may have been cleaned up)")
            return
        for line in lines:
            click.echo(line.rstrip())
        return

    containers = get_containers(client, app_name)
    if not containers:
        click.echo("No running containers found.")
        return

    if service:
        containers = [c for c in containers if service in c.get("name", "")]
        if not containers:
            click.echo(f"No container found matching service '{service}'")
            available = get_containers(client, app_name)
            if available:
                click.echo("Available services:")
                for c in available:
                    name = c.get("name", "?").replace(f"{app_name}-", "").rstrip("-1234567890")
                    click.echo(f"  {name}")
            return

    for c in containers:
        cid = c.get("containerId", "")
        if not cid:
            continue
        short = c.get("name", "?").replace(f"{app_name}-", "").rstrip("-1234567890")
        fetched = fetch_container_logs(url, token, cid, tail=tail, since=since)
        if len(containers) > 1:
            click.echo(f"--- {short} (container: {cid}) ---")
        for line in fetched:
            click.echo(line.rstrip())
        if len(containers) > 1:
            click.echo()
    timer.summary("Done.")
