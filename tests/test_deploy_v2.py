"""Tests for deploy command v2 — timestamped LDD output."""

from unittest.mock import MagicMock, patch

import httpx
from click.testing import CliRunner

from dokployctl.cli import cli


def _mock_response(data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    resp.text = str(data)
    return resp


@patch("dokployctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.deploy.make_client")
@patch("dokployctl.deploy.api_call")
def test_deploy_has_timestamps(mock_api, mock_client, mock_config, tmp_path):
    """Deploy output must include [MM:SS] timestamp on every line."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    mock_api.side_effect = [
        _mock_response({"composeFile": "x" * 100, "sourceType": "raw"}),  # compose.update
        _mock_response([{"deploymentId": "old"}]),  # deployment.allByCompose (snapshot)
        _mock_response({}),  # compose.deploy
        _mock_response([{"deploymentId": "new", "status": "done"}]),  # poll
        _mock_response({"appName": "test-app"}),  # compose.one (health)
    ]

    with (
        patch(
            "dokployctl.deploy.get_containers",
            return_value=[{"name": "test-app-web-1", "state": "running", "status": "Up 1m (healthy)", "containerId": "abc123"}],
        ),
        patch("dokployctl.deploy.verify_container_health", return_value=True),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    assert "[00:00]" in result.output
    assert "total)" in result.output


@patch("dokployctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.deploy.make_client")
@patch("dokployctl.deploy.api_call")
def test_deploy_summary_success(mock_api, mock_client, mock_config, tmp_path):
    """Deploy summary must include 'Deploy succeeded.' on success."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    mock_api.side_effect = [
        _mock_response({"composeFile": "x" * 100, "sourceType": "raw"}),
        _mock_response([{"deploymentId": "old"}]),
        _mock_response({}),
        _mock_response([{"deploymentId": "new", "status": "done"}]),
        _mock_response({"appName": "test-app"}),
    ]

    with patch("dokployctl.deploy.get_containers", return_value=[]), patch("dokployctl.deploy.verify_container_health", return_value=True):
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    assert "Deploy succeeded" in result.output
    assert "total)" in result.output


@patch("dokployctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.deploy.make_client")
@patch("dokployctl.deploy.api_call")
def test_sync_has_timestamps(mock_api, mock_client, mock_config, tmp_path):
    """Sync output must include [MM:SS] timestamps."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    mock_api.return_value = _mock_response({"composeFile": "x" * 100, "sourceType": "raw"})

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "test-id", str(compose)])

    assert "[00:00]" in result.output


@patch("dokployctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.deploy.make_client")
@patch("dokployctl.deploy.api_call")
def test_deploy_failure_shows_log_and_hint(mock_api, mock_client, mock_config, tmp_path):
    """On deploy failure, output includes deploy log header and a hint."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  worker:\n    image: myapp")

    mock_api.side_effect = [
        _mock_response({"composeFile": "x" * 100, "sourceType": "raw"}),  # compose.update
        _mock_response([{"deploymentId": "old"}]),  # snapshot
        _mock_response({}),  # compose.deploy
        _mock_response(
            [
                {  # poll — error
                    "deploymentId": "new",
                    "status": "error",
                    "errorMessage": "exit code 1",
                    "logPath": "/logs/deploy.log",
                }
            ]
        ),
        _mock_response({"appName": "test-app"}),  # compose.one
    ]

    with (
        patch("dokployctl.deploy.show_deploy_log"),
        patch(
            "dokployctl.deploy.get_containers",
            return_value=[
                {
                    "name": "test-app-worker-1",
                    "state": "exited",
                    "status": "Exited (1) 30s ago",
                    "containerId": "a1b2c3d4ef56",
                }
            ],
        ),
        patch("dokployctl.deploy.show_problem_logs"),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    # Should exit non-zero
    assert result.exit_code != 0
    # Should show deploy failed message with timestamp
    assert "[00:" in result.output
    # Summary should mention failure
    assert "failed" in result.output.lower()


@patch("dokployctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.deploy.make_client")
@patch("dokployctl.deploy.api_call")
def test_deploy_poll_status_shown(mock_api, mock_client, mock_config, tmp_path):
    """Each poll iteration must emit a timestamped line with status."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    mock_api.side_effect = [
        _mock_response({"composeFile": "x" * 100, "sourceType": "raw"}),
        _mock_response([{"deploymentId": "old"}]),
        _mock_response({}),
        _mock_response([{"deploymentId": "new", "status": "running"}]),  # first poll
        _mock_response([{"deploymentId": "new", "status": "done"}]),  # second poll
        _mock_response({"appName": "test-app"}),
    ]

    with (
        patch("dokployctl.deploy.get_containers", return_value=[]),
        patch("dokployctl.deploy.verify_container_health", return_value=True),
        patch("time.sleep"),
    ):  # skip actual sleeping
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    assert "status=running" in result.output
    assert "status=done" in result.output


@patch("dokployctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.deploy.make_client")
@patch("dokployctl.deploy.api_call")
def test_sync_shows_char_count(mock_api, mock_client, mock_config, tmp_path):
    """Sync output must mention char count and sourceType."""
    compose = tmp_path / "docker-compose.prod.yml"
    content = "version: '3'\nservices:\n  web:\n    image: nginx"
    compose.write_text(content)

    mock_api.return_value = _mock_response({"composeFile": "Y" * 200, "sourceType": "raw"})

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "test-id", str(compose)])

    assert "sourceType=raw" in result.output
    assert "200" in result.output
