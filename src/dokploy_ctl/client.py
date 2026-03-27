"""Config loading, HTTP client, and API call helpers."""

import json
import os
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


_DASH_ID_PLACEHOLDER = "__DOKPLOY_DASH_ID__"


class DashSafeCommand(click.Command):
    """Command subclass that handles Dokploy IDs starting with '-'.

    Click normally interprets '-Gxyz...' as a short option flag.
    This detects dash-prefixed args that aren't known options,
    swaps them with a placeholder for parsing, then restores the real value.
    """

    def _known_short_opts(self) -> set[str]:
        opts: set[str] = set()
        for param in self.params:
            if isinstance(param, click.Option):
                for o in param.opts + param.secondary_opts:
                    if o.startswith("-") and not o.startswith("--"):
                        opts.add(o)
        return opts

    def _is_dash_id(self, arg: str, known_short: set[str]) -> bool:
        return arg.startswith("-") and not arg.startswith("--") and len(arg) > 2 and arg[:2] not in known_short

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        known_short = self._known_short_opts()
        new_args = list(args)
        original_value: str | None = None

        for i, arg in enumerate(new_args):
            if arg == "--":
                break
            if self._is_dash_id(arg, known_short):
                original_value = arg
                new_args[i] = _DASH_ID_PLACEHOLDER
                break

        result = super().parse_args(ctx, new_args)

        if original_value is not None:
            for key, val in ctx.params.items():
                if val == _DASH_ID_PLACEHOLDER:
                    ctx.params[key] = original_value
        return result


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
            f"\nSetup:\n  dokploy-ctl login --url <url> --token <token>\n"
            f"  Or manually:\n  mkdir -p {config_dir}\n"
            f"  echo 'YOUR_TOKEN' > {token_path}\n"
            f"  echo 'https://your-dokploy-url' > {url_path}",
            err=True,
        )
        sys.exit(1)

    token = token_path.read_text().strip()
    url = url_path.read_text().strip().rstrip("/")

    if not url or not url.startswith(("http://", "https://")):
        click.echo(f"error: invalid URL in {url_path}: '{url}'", err=True)
        click.echo("Fix: dokploy-ctl login --url https://your-dokploy-url --token <token>", err=True)
        sys.exit(1)
    if not token:
        click.echo(f"error: empty token in {token_path}", err=True)
        sys.exit(1)

    return url, token


def make_client(url: str, token: str) -> httpx.Client:
    verify = os.environ.get("DOKPLOY_INSECURE", "").lower() not in ("1", "true", "yes")
    return httpx.Client(
        base_url=url,
        headers={"x-api-key": token, "Content-Type": "application/json"},
        timeout=TIMEOUT,
        verify=verify,
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
