"""Status command."""

import click

from dokploy_ctl.client import DOKPLOY_ID, DashSafeCommand
from dokploy_ctl.dokploy import ContainerInfo, DokployClient
from dokploy_ctl.hints import hint_no_containers, hint_unhealthy
from dokploy_ctl.timer import Timer


def _container_ok(c: ContainerInfo) -> bool:
    """Container is healthy if running+healthy, running without healthcheck, or one-shot success."""
    return (
        (c.state == "exited" and "Exited (0)" in c.raw_status)
        or (c.state == "running" and c.health == "healthy")
        or (c.state == "running" and c.health == "\u2014" and "(unhealthy)" not in c.raw_status)
    )


def _format_container_table(containers: list[ContainerInfo]) -> str:
    header = f"  {'SERVICE':<20} {'STATE':<10} {'HEALTH':<12} {'IMAGE':<45} {'UPTIME':<8} CONTAINER ID"
    rows = [f"  {c.service:<20} {c.state:<10} {c.health:<12} {c.image:<45} {c.uptime:<8} {c.container_id[:8]}" for c in containers]
    return "\n".join([header, *rows])


@click.command(cls=DashSafeCommand)
@click.argument("compose_id", type=DOKPLOY_ID)
@click.option("--live", "-l", is_flag=True, hidden=True, help="[deprecated] Containers are always shown now.")
def status(compose_id: str, live: bool) -> None:
    """Show compose app status."""
    timer = Timer()

    if live:
        click.echo("Warning: --live is deprecated; containers are always shown.")

    timer.log(f"Fetching compose app {compose_id}...")

    client = DokployClient()
    comp = client.get_compose(compose_id)

    click.echo(f"\nName:         {comp.name}")
    click.echo(f"App name:     {comp.app_name}")
    click.echo(f"Status:       {comp.status}")
    click.echo(f"Compose:      {len(comp.compose_file):,} chars")
    env_keys = [line.split("=")[0] for line in comp.env.strip().splitlines() if "=" in line]
    click.echo(f"Env keys:     {', '.join(env_keys) if env_keys else '(none)'}")

    if comp.deployments:
        latest = comp.deployments[0]
        click.echo(f"\nLast deploy:  {latest.title} ({latest.status})")
        click.echo(f"  at:         {latest.created_at}")
        if latest.error_message:
            click.echo(f"  error:      {latest.error_message}")

    containers = client.get_containers(comp.app_name)

    click.echo("\nContainers:")
    if not containers:
        click.echo("  (none found)")
        click.echo("")
        click.echo(hint_no_containers(compose_id))
        timer.summary("No containers found.")
        return

    click.echo(_format_container_table(containers))

    unhealthy = [c for c in containers if not _container_ok(c)]
    healthy_count = len(containers) - len(unhealthy)

    click.echo("")

    for c in unhealthy:
        click.echo(hint_unhealthy(compose_id, c.service))

    if unhealthy:
        timer.summary(f"{healthy_count}/{len(containers)} containers healthy.")
    else:
        timer.summary(f"All {len(containers)} containers healthy.")
