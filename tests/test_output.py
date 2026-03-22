from dokploy_ctl.output import format_container_row, format_container_table, parse_health, parse_service_name, parse_uptime


def test_parse_service_name():
    assert parse_service_name("compose-connect-back-end-alarm-zgu447-worker-1", "compose-connect-back-end-alarm-zgu447") == "worker"


def test_parse_service_name_strips_trailing_numbers():
    assert parse_service_name("app-db-1", "app") == "db"


def test_parse_health_healthy():
    assert parse_health("Up 2 hours (healthy)") == "healthy"


def test_parse_health_unhealthy():
    assert parse_health("Up 2 hours (unhealthy)") == "unhealthy"


def test_parse_health_starting():
    assert parse_health("Up 2 hours (health: starting)") == "starting"


def test_parse_health_no_healthcheck():
    assert parse_health("Up 2 hours") == "—"


def test_parse_health_exited():
    assert parse_health("Exited (0) 5 min ago") == "—"


def test_parse_uptime_running():
    assert parse_uptime("Up 2 hours (healthy)") == "2h"


def test_parse_uptime_exited():
    assert parse_uptime("Exited (0) 5 min ago") == "—"


def test_format_container_row():
    c = {
        "name": "app-worker-1",
        "state": "running",
        "status": "Up 2 hours (healthy)",
        "containerId": "abc123def456",
        "image": "ghcr.io/iorlas/app:main-abc1234",
    }
    row = format_container_row(c, "app")
    assert "worker" in row
    assert "running" in row
    assert "healthy" in row
    assert "abc123de" in row  # truncated container ID (first 8 chars)
    assert "ghcr.io/iorlas/app:main-abc1234" in row


def test_format_container_table_has_headers():
    containers = [
        {
            "name": "app-worker-1",
            "state": "running",
            "status": "Up 2 hours (healthy)",
            "containerId": "abc123def456",
            "image": "ghcr.io/iorlas/app:tag",
        },
    ]
    table = format_container_table(containers, "app")
    assert "SERVICE" in table
    assert "STATE" in table
    assert "HEALTH" in table
    assert "IMAGE" in table
    assert "UPTIME" in table
    assert "CONTAINER ID" in table
    assert "worker" in table
