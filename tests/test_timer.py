from dokployctl.timer import Timer


def test_timer_starts_at_zero():
    t = Timer()
    assert t.stamp() == "[00:00]"


def test_timer_advances():
    t = Timer()
    t._start -= 65  # simulate 1m5s elapsed
    assert t.stamp() == "[01:05]"


def test_timer_log_returns_stamped_message():
    t = Timer()
    result = t.log("Syncing...")
    assert result == "[00:00] Syncing..."


def test_timer_summary_includes_total():
    t = Timer()
    t._start -= 12  # simulate 12s
    result = t.summary("Deploy succeeded.")
    assert "[00:12]" in result
    assert "(12s total)" in result
    assert "Deploy succeeded." in result
