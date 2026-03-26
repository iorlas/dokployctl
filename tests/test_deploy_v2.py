"""Tests for deploy and sync commands — timestamped LDD output."""

from unittest.mock import MagicMock, patch

import httpx
from click.testing import CliRunner

from dokploy_ctl.cli import cli
from dokploy_ctl.dokploy import ContainerInfo, Deployment


def _mock_response(data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    resp.text = str(data)
    return resp


def _container(cid, service, state="running", health="healthy", raw_status="Up 1m (healthy)"):
    return ContainerInfo(
        container_id=cid,
        service=service,
        state=state,
        health=health,
        image="img",
        uptime="1m",
        raw_status=raw_status,
    )


def _deployment(dep_id, status="done", error_message="", log_path=""):
    dep = MagicMock(spec=Deployment)
    dep.deployment_id = dep_id
    dep.status = status
    dep.error_message = error_message
    dep.log_path = log_path
    return dep


def _setup_deploy_client(mock_client_cls, *, pre_containers=None, poll_containers=None, poll_deps=None):
    """Helper: wire up a DokployClient mock for deploy tests.

    poll_containers: list of lists — one list per poll cycle call.
    """
    client = mock_client_cls.return_value
    client.url = "https://example.com"
    client.token = "tok"

    mock_updated = MagicMock()
    mock_updated.compose_file = "x" * 100
    mock_updated.env = ""
    client.update_compose.return_value = mock_updated

    mock_app = MagicMock()
    mock_app.app_name = "test-app"
    client.get_compose.return_value = mock_app

    client.trigger_deploy.return_value = None

    if poll_deps is None:
        poll_deps = [_deployment("new", status="done")]
    client.get_latest_deployment.side_effect = [_deployment("old"), *poll_deps]

    if pre_containers is None:
        pre_containers = []
    if poll_containers is None:
        # Default: one poll cycle returning one healthy container
        poll_containers = [[_container("c1", "web")]]
    # poll_containers is a list-of-lists
    client.get_containers.side_effect = [pre_containers, *poll_containers]

    return client


def test_deploy_has_timestamps(tmp_path):
    """Deploy output must include [MM:SS] timestamp on every line."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    with patch("dokploy_ctl.deploy.DokployClient") as mock_client_cls:
        _setup_deploy_client(mock_client_cls)
        with patch("time.sleep"):
            runner = CliRunner()
            result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    assert "[00:00]" in result.output
    assert "total)" in result.output


def test_deploy_summary_success(tmp_path):
    """Deploy summary must include 'Deploy succeeded.' on success."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    with patch("dokploy_ctl.deploy.DokployClient") as mock_client_cls:
        _setup_deploy_client(mock_client_cls)
        with patch("time.sleep"):
            runner = CliRunner()
            result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    assert "Deploy succeeded" in result.output
    assert "total)" in result.output


@patch("dokploy_ctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokploy_ctl.deploy.make_client")
@patch("dokploy_ctl.deploy.api_call")
def test_sync_has_timestamps(mock_api, mock_client, mock_config, tmp_path):
    """Sync output must include [MM:SS] timestamps."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    mock_api.return_value = _mock_response({"composeFile": "x" * 100, "sourceType": "raw"})

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "test-id", str(compose)])

    assert "[00:00]" in result.output


def test_deploy_failure_shows_log_and_hint(tmp_path):
    """On deploy failure, output includes deploy log header and a hint."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  worker:\n    image: myapp")

    exited_container = _container("c1", "worker", state="exited", health="\u2014", raw_status="Exited (1) 30s ago")

    with (
        patch("dokploy_ctl.deploy.DokployClient") as mock_client_cls,
        patch("dokploy_ctl.deploy.show_deploy_log"),
        patch("dokploy_ctl.deploy.show_problem_logs"),
    ):
        _setup_deploy_client(
            mock_client_cls,
            pre_containers=[],
            poll_containers=[[exited_container]],
            poll_deps=[_deployment("new", status="error", error_message="exit code 1", log_path="/logs/deploy.log")],
        )
        with patch("time.sleep"):
            runner = CliRunner()
            result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    # Should exit non-zero
    assert result.exit_code != 0
    # Should show deploy failed message with timestamp
    assert "[00:" in result.output
    # Summary should mention failure
    assert "failed" in result.output.lower()


def test_deploy_transitions_not_dumb_polling(tmp_path):
    """Deploy must NOT emit 'status=running' repeated — old dumb polling pattern."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    with patch("dokploy_ctl.deploy.DokployClient") as mock_client_cls:
        _setup_deploy_client(
            mock_client_cls,
            pre_containers=[],
            poll_containers=[_container("c1", "web")],
            poll_deps=[
                _deployment("new", status="running"),
                _deployment("new", status="done"),
            ],
        )
        # Two containers calls for two poll cycles
        client = mock_client_cls.return_value
        client.get_containers.side_effect = [
            [],  # pre-deploy
            [],  # poll 1 (running)
            [_container("c1", "web")],  # poll 2 (done + healthy)
        ]

        with patch("time.sleep"):
            runner = CliRunner()
            result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    # New smart polling: no "status=running" lines
    assert "status=running" not in result.output
    assert result.exit_code == 0


@patch("dokploy_ctl.deploy.load_config", return_value=("https://example.com", "token"))
@patch("dokploy_ctl.deploy.make_client")
@patch("dokploy_ctl.deploy.api_call")
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
