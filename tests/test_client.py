from dokployctl.client import load_config, make_client


def test_load_config_success(config_dir):
    url, token = load_config(config_dir)
    assert url == "https://dokploy.example.com"
    assert token == "test-token-123"


def test_load_config_strips_trailing_slash(config_dir):
    (config_dir / "url").write_text("https://example.com/  \n")
    url, _ = load_config(config_dir)
    assert url == "https://example.com"


def test_load_config_missing_files(empty_config_dir):
    import pytest

    with pytest.raises(SystemExit):
        load_config(empty_config_dir)


def test_make_client_sets_headers():
    client = make_client("https://example.com", "tok123")
    assert client.headers["x-api-key"] == "tok123"
    assert "json" in client.headers["content-type"]
