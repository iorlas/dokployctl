import pytest

from dokploy_ctl.env import resolve_env


def test_resolve_env_returns_none_when_no_flag():
    """Default: no env resolution even if compose has ${VAR} refs."""
    result = resolve_env(env_flag=False, env_file=None, compose_content="image: ${TAG}")
    assert result is None


def test_resolve_env_resolves_when_flag_set(monkeypatch):
    monkeypatch.setenv("TAG", "v1")
    result = resolve_env(env_flag=True, env_file=None, compose_content="image: ${TAG}")
    assert result is not None
    assert "TAG=v1" in result


def test_resolve_env_errors_on_both_flags():
    with pytest.raises(SystemExit):
        resolve_env(env_flag=True, env_file="some.env", compose_content="")


def test_resolve_env_no_flag_no_file_returns_none():
    result = resolve_env(env_flag=False, env_file=None, compose_content="no vars here")
    assert result is None
