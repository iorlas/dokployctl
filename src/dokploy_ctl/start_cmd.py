"""Start command."""

import time

import click

from dokploy_ctl.client import DOKPLOY_ID, DashSafeCommand
from dokploy_ctl.dokploy import ContainerInfo, DokployClient
from dokploy_ctl.hints import hint_unhealthy
from dokploy_ctl.timer import Timer


def _container_ok(c: ContainerInfo) -> bool:
    """Container is healthy if running+healthy, running without healthcheck, or one-shot success."""
    return (
        (c.state == "exited" and "Exited (0)" in c.raw_status)
        or (c.state == "running" and c.health == "healthy")
        or (c.state == "running" and c.health == "\u2014" and "(unhealthy)" not in c.raw_status)
    )


def _container_converging(c: ContainerInfo) -> bool:
    return c.health == "starting" or c.state == "restarting"


def _verify_health(client: DokployClient, app_name: str, timeout: int = 120) -> bool:
    max_attempts = timeout // 5
    for i in range(1, max_attempts + 1):
        containers = client.get_containers(app_name)
        if not containers:
            click.echo(f"  [health {i}/{max_attempts}] No containers found for {app_name}")
            time.sleep(5)
            continue

        all_ok = all(_container_ok(c) for c in containers)
        still_converging = any(_container_converging(c) for c in containers)

        labels = [f"{c.service}={'ok' if _container_ok(c) else c.health if c.health != chr(0x2014) else c.state}" for c in containers]
        click.echo(f"  [health {i}/{max_attempts}] {', '.join(labels)}")

        if all_ok:
            return True
        if not still_converging:
            return False

        time.sleep(5)

    return False


@click.command(cls=DashSafeCommand)
@click.argument("compose_id", type=DOKPLOY_ID)
def start(compose_id: str) -> None:
    """Start a stopped compose app and verify health."""
    timer = Timer()
    client = DokployClient()

    timer.log(f"Starting compose {compose_id}...")
    client.start_compose(compose_id)

    comp = client.get_compose(compose_id)
    app_name = comp.app_name
    if not app_name:
        timer.summary("Started (no appName for health check).")
        return

    timer.log("Verifying container health...")
    healthy = _verify_health(client, app_name, timeout=120)
    if healthy:
        timer.summary("All containers healthy. Started.")
    else:
        containers = client.get_containers(app_name)
        for c in containers:
            if not _container_ok(c):
                click.echo(hint_unhealthy(compose_id, c.service))
        timer.summary("Started but not all containers healthy.")
        raise SystemExit(1)
