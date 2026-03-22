"""Stop command."""

import click

from dokploy_ctl.client import DOKPLOY_ID, _err, api_call, load_config, make_client
from dokploy_ctl.hints import hint_restart
from dokploy_ctl.timer import Timer


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
