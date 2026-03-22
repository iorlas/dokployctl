from dokploy_ctl.containers import _container_converging, _container_ok, _is_one_shot


def test_one_shot_exited_0():
    assert _is_one_shot({"state": "exited", "status": "Exited (0) 5 min ago"})


def test_not_one_shot_exited_1():
    assert not _is_one_shot({"state": "exited", "status": "Exited (1) 5 min ago"})


def test_container_ok_healthy():
    assert _container_ok({"state": "running", "status": "Up 5 min (healthy)"})


def test_container_ok_no_healthcheck():
    assert _container_ok({"state": "running", "status": "Up 5 min"})


def test_container_not_ok_unhealthy():
    assert not _container_ok({"state": "running", "status": "Up 5 min (unhealthy)"})


def test_container_converging_starting():
    assert _container_converging({"state": "running", "status": "Up 5 min (health: starting)"})


def test_container_converging_restarting():
    assert _container_converging({"state": "restarting", "status": ""})


def test_container_not_converging_healthy():
    assert not _container_converging({"state": "running", "status": "Up 5 min (healthy)"})
