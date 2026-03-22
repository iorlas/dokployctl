"""CLI entry point — click group + login command."""

import click

from dokploy_ctl.api_cmd import api
from dokploy_ctl.client import DEFAULT_CONFIG_DIR
from dokploy_ctl.deploy import deploy, sync
from dokploy_ctl.find_cmd import find
from dokploy_ctl.init_cmd import init
from dokploy_ctl.logs import logs
from dokploy_ctl.start_cmd import start
from dokploy_ctl.status import status
from dokploy_ctl.stop_cmd import stop


@click.group(invoke_without_command=True)
@click.version_option(package_name="dokploy-ctl")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """dokploy-ctl — CLI for Dokploy deployments."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(find)


@cli.command()
@click.option("--url", required=True, help="Dokploy instance URL")
@click.option("--token", required=True, help="API token")
def login(url: str, token: str) -> None:
    """Store Dokploy credentials."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (DEFAULT_CONFIG_DIR / "url").write_text(url.rstrip("/") + "\n")
    (DEFAULT_CONFIG_DIR / "token").write_text(token + "\n")
    click.echo(f"Saved credentials to {DEFAULT_CONFIG_DIR}")


cli.add_command(api)
cli.add_command(find)
cli.add_command(status)
cli.add_command(logs)
cli.add_command(deploy)
cli.add_command(sync)
cli.add_command(init)
cli.add_command(stop)
cli.add_command(start)
