# tests/test_stop_start.py
from unittest.mock import MagicMock, patch

import httpx
from click.testing import CliRunner

from dokployctl.cli import cli


def _mock_response(data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    return resp


@patch("dokployctl.stop_cmd.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.stop_cmd.make_client")
@patch("dokployctl.stop_cmd.api_call")
def test_stop_succeeds(mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response({})
    runner = CliRunner()
    result = runner.invoke(cli, ["stop", "test-id"])
    assert result.exit_code == 0
    assert "Stopping" in result.output
    assert "Stopped" in result.output
    assert "dokployctl start test-id" in result.output


@patch("dokployctl.stop_cmd.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.stop_cmd.make_client")
@patch("dokployctl.stop_cmd.api_call")
def test_stop_api_error(mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response({}, status_code=500)
    runner = CliRunner()
    result = runner.invoke(cli, ["stop", "test-id"])
    assert result.exit_code != 0


@patch("dokployctl.start_cmd.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.start_cmd.make_client")
@patch("dokployctl.start_cmd.api_call")
@patch("dokployctl.start_cmd.verify_container_health", return_value=True)
def test_start_succeeds(mock_health, mock_api, mock_client, mock_config):
    mock_api.side_effect = [
        _mock_response({}),  # compose.start
        _mock_response({"appName": "test-app"}),  # compose.one
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["start", "test-id"])
    assert result.exit_code == 0
    assert "Starting" in result.output
    assert "healthy" in result.output.lower() or "Started" in result.output
