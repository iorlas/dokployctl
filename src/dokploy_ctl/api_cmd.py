"""Raw API call command."""

import json

import click

from dokploy_ctl.client import api_call, load_config, make_client, print_response


@click.command()
@click.argument("endpoint")
@click.option("--data", "-d", default=None, help="JSON body (POST) or query params (GET with -X GET)")
@click.option("--method", "-X", default=None, help="HTTP method (default: POST if --data, GET otherwise)")
def api(endpoint: str, data: str | None, method: str | None) -> None:
    """Raw API call (like gh api)."""
    url, token = load_config()
    client = make_client(url, token)
    parsed = json.loads(data) if data else None
    m = (method or ("POST" if parsed else "GET")).upper()
    resp = api_call(client, m, endpoint, parsed)
    print_response(resp)
