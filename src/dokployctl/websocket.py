"""WebSocket helpers for fetching container and deploy logs."""

import asyncio
import ssl
import urllib.parse

import websockets

from dokployctl.client import _err


def _ws_url(base_url: str) -> str:
    return base_url.replace("https://", "wss://").replace("http://", "ws://")


def _fetch_ws(url: str, token: str, recv_timeout: float = 5.0) -> list[str]:
    """Connect to WebSocket, collect all messages, return as lines."""

    async def _inner() -> list[str]:
        lines: list[str] = []
        ssl_ctx = ssl.create_default_context()
        try:
            async with websockets.connect(
                url,
                ssl=ssl_ctx,
                additional_headers={"x-api-key": token},
                open_timeout=10,
                close_timeout=3,
            ) as ws:
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                        text = msg if isinstance(msg, str) else msg.decode("utf-8", errors="replace")
                        lines.append(text)
                    except TimeoutError:
                        break
                    except websockets.exceptions.ConnectionClosed:
                        break
        except Exception as e:  # noqa: BLE001
            _err(f"warning: WebSocket error: {e}")
        return lines

    return asyncio.run(_inner())


def fetch_container_logs(
    base_url: str,
    token: str,
    container_id: str,
    tail: int = 50,
    since: str = "5m",
    recv_timeout: float = 5.0,
) -> list[str]:
    ws_base = _ws_url(base_url)
    url = f"{ws_base}/docker-container-logs?containerId={container_id}&tail={tail}&since={since}"
    return _fetch_ws(url, token, recv_timeout)


def fetch_deploy_log(
    base_url: str,
    token: str,
    log_path: str,
    recv_timeout: float = 5.0,
) -> list[str]:
    ws_base = _ws_url(base_url)
    url = f"{ws_base}/listen-deployment?logPath={urllib.parse.quote(log_path)}"
    return _fetch_ws(url, token, recv_timeout)
