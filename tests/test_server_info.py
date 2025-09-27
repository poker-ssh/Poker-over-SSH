import os

from poker.server_info import format_motd, get_server_info, load_env_file
from poker.version import get_version_info


def test_load_env_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("SERVER_ENV=Production\nSERVER_HOST=example.com\n# comment\nNAME=value=with=equals\n")
    env_vars = load_env_file(str(env_path))
    assert env_vars["SERVER_ENV"] == "Production"
    assert env_vars["SERVER_HOST"] == "example.com"
    # Ensure values with multiple equals are preserved
    assert env_vars["NAME"] == "value=with=equals"


def test_get_server_info_uses_environment(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("SERVER_ENV=Staging\nSERVER_PORT=10022\n")

    monkeypatch.setenv("SERVER_ENV", "Public Stable")
    monkeypatch.setenv("SERVER_HOST", "poker.example")
    monkeypatch.setenv("SERVER_PORT", "22222")
    monkeypatch.setenv("SERVER_NAME", "Prod Poker")
    monkeypatch.chdir(tmp_path)

    info = get_server_info()
    assert info["server_env"] == "Public Stable"
    assert info["server_host"] == "poker.example"
    assert info["server_port"] == "22222"
    assert info["server_name"] == "Prod Poker"
    assert info["ssh_connection_string"] == "poker.example -p 22222"
    version_info = get_version_info()
    for key, value in version_info.items():
        assert info[key] == value

    monkeypatch.setenv("SERVER_PORT", "22")
    info_default_port = get_server_info()
    assert info_default_port["ssh_connection_string"] == "poker.example"


def test_format_motd_includes_version(monkeypatch):
    monkeypatch.setattr("poker.terminal_ui.Colors.GREEN", "<GREEN>")
    monkeypatch.setattr("poker.terminal_ui.Colors.YELLOW", "<YELLOW>")
    monkeypatch.setattr("poker.terminal_ui.Colors.CYAN", "<CYAN>")
    monkeypatch.setattr("poker.terminal_ui.Colors.BOLD", "<BOLD>")
    monkeypatch.setattr("poker.terminal_ui.Colors.RESET", "<RESET>")
    monkeypatch.setattr("poker.terminal_ui.Colors.DIM", "<DIM>")

    motd = format_motd({
        "server_name": "Poker",
        "server_env": "Public Stable",
        "ssh_connection_string": "example.com -p 22222",
        "version": "1.0.0",
        "build_date": "today",
    })
    assert "Poker" in motd
    assert "Public Stable" in motd
    assert "1.0.0" in motd
    assert "today" in motd