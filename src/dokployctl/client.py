"""Config loading, HTTP client, and API call helpers."""

import json
import sys
from pathlib import Path

import click
import httpx

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "dokploy"
TIMEOUT = 30.0


class DokployID(click.ParamType):
    """Click type that accepts Dokploy IDs, including those starting with '-'."""

    name = "id"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:  # noqa: ARG002
        return value


DOKPLOY_ID = DokployID()


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> tuple[str, str]:
    """Return (base_url, token). Exit with clear error if missing."""
    token_path = config_dir / "token"
    url_path = config_dir / "url"

    errors = []
    if not token_path.exists():
        errors.append(f"Missing token file: {token_path}")
    if not url_path.exists():
        errors.append(f"Missing URL file: {url_path}")
    if errors:
        for e in errors:
            click.echo(f"error: {e}", err=True)
        click.echo(
            f"\nSetup:\n  dokployctl login --url <url> --token <token>\n"
            f"  Or manually:\n  mkdir -p {config_dir}\n"
            f"  echo 'YOUR_TOKEN' > {token_path}\n"
            f"  echo 'https://your-dokploy-url' > {url_path}",
            err=True,
        )
        sys.exit(1)

    token = token_path.read_text().strip()
    url = url_path.read_text().strip().rstrip("/")
    return url, token


def make_client(url: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=url,
        headers={"x-api-key": token, "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )


def api_call(client: httpx.Client, method: str, endpoint: str, data: dict | None = None) -> httpx.Response:
    """Make an API call. Endpoint is like 'compose.one' (no /api/ prefix)."""
    url = f"/api/{endpoint}"
    if method.upper() == "GET":
        return client.get(url, params=data)
    return client.post(url, json=data)


def _err(msg: str) -> None:
    """Print to stderr with stdout flush (prevents CI interleaving)."""
    sys.stdout.flush()
    click.echo(msg, err=True)


def print_response(resp: httpx.Response) -> None:
    """Print response JSON. Exit 1 on HTTP error."""
    try:
        click.echo(json.dumps(resp.json(), indent=2))
    except Exception:  # noqa: BLE001
        click.echo(resp.text)
    if resp.is_error:
        _err(f"\nerror: HTTP {resp.status_code}")
        sys.exit(1)
