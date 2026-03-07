import pytest


@pytest.fixture
def config_dir(tmp_path):
    """Temporary config directory with valid token and URL."""
    token_file = tmp_path / "token"
    url_file = tmp_path / "url"
    token_file.write_text("test-token-123")
    url_file.write_text("https://dokploy.example.com")
    return tmp_path


@pytest.fixture
def empty_config_dir(tmp_path):
    """Config directory with no files."""
    return tmp_path
