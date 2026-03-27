"""Restart command — restart a specific service or all services."""

import click

from dokploy_ctl.client import DOKPLOY_ID, DashSafeCommand
from dokploy_ctl.dokploy import DokployClient
from dokploy_ctl.timer import Timer


@click.command(cls=DashSafeCommand)
@click.argument("compose_id", type=DOKPLOY_ID)
@click.option("--service", "-s", default=None, help="Restart a specific service (by name)")
def restart(compose_id: str, service: str | None) -> None:
    """Restart containers. Without --service, redeploys the compose app."""
    timer = Timer()
    client = DokployClient()

    if service:
        comp = client.get_compose(compose_id)
        app_name = comp.app_name
        containers = client.get_containers(app_name)

        matching = [c for c in containers if service in c.service]
        if not matching:
            click.echo(f"error: no container found matching service '{service}'", err=True)
            available = [c.service for c in containers]
            if available:
                click.echo(f"Available services: {', '.join(sorted(set(available)))}")
            raise SystemExit(1)

        for c in matching:
            timer.log(f"Restarting {c.service} (container: {c.container_id[:8]})...")
            client.restart_container(c.container_id)

        timer.summary(f"Restarted {len(matching)} container(s).")
    else:
        # Redeploy the whole compose app
        timer.log(f"Redeploying compose {compose_id}...")
        client.redeploy_compose(compose_id)
        timer.summary("Redeploy triggered.")
        click.echo(f"\nHint: Monitor with: dokploy-ctl status {compose_id}")
