from dokploy_ctl.hints import hint_deploy_failed, hint_no_containers, hint_restart, hint_stopped, hint_unhealthy


def test_hint_unhealthy_includes_compose_id():
    h = hint_unhealthy("IWcY", "worker")
    assert "IWcY" in h
    assert "worker" in h
    assert "dokploy-ctl logs" in h


def test_hint_deploy_failed_includes_log_command():
    h = hint_deploy_failed("IWcY", "worker", "exited(1)")
    assert "dokploy-ctl logs IWcY --service worker" in h


def test_hint_restart():
    h = hint_restart("IWcY")
    assert "dokploy-ctl start IWcY" in h


def test_hint_stopped():
    h = hint_stopped("IWcY")
    assert "dokploy-ctl start IWcY" in h


def test_hint_no_containers():
    h = hint_no_containers("IWcY")
    assert "dokploy-ctl start IWcY" in h
