"""Runtime configuration: token strength, ports, log level."""

from __future__ import annotations

import pytest

from mocksite.config import MIN_TOKEN_CHARS, ConfigError, Settings

GOOD_TOKEN = "a" * MIN_TOKEN_CHARS


def _env(**overrides: str) -> dict[str, str]:
    return {"MOCKSITE_TOKEN": GOOD_TOKEN, **overrides}


def test_defaults() -> None:
    settings = Settings.from_env(_env())
    assert settings.site_port == 9000
    assert settings.admin_port == 9001
    assert settings.site_host == "0.0.0.0"
    assert settings.log_level == "info"


def test_origins_are_derived() -> None:
    settings = Settings.from_env(_env(MOCKSITE_SITE_HOST="127.0.0.1"))
    assert settings.site_origin == "http://127.0.0.1:9000"
    assert settings.admin_origin == "http://0.0.0.0:9001"


def test_missing_token_refuses_to_start() -> None:
    with pytest.raises(ConfigError, match="MOCKSITE_TOKEN"):
        Settings.from_env({})


@pytest.mark.parametrize("token", ["short", "a" * (MIN_TOKEN_CHARS - 1)])
def test_short_token_refuses_to_start(token: str) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env({"MOCKSITE_TOKEN": token})


def test_whitespace_does_not_count_towards_token_length() -> None:
    padded = " " * 40 + "abc"
    with pytest.raises(ConfigError):
        Settings.from_env({"MOCKSITE_TOKEN": padded})


def test_token_with_internal_whitespace_is_still_long_enough() -> None:
    token = "ab cd " * 10
    assert Settings.from_env({"MOCKSITE_TOKEN": token}).token == token


def test_same_ports_rejected() -> None:
    with pytest.raises(ConfigError, match="must differ"):
        Settings.from_env(_env(MOCKSITE_SITE_PORT="9001", MOCKSITE_ADMIN_PORT="9001"))


@pytest.mark.parametrize("raw", ["0", "65536", "-1", "abc", "90.0"])
def test_invalid_ports_rejected(raw: str) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(_env(MOCKSITE_SITE_PORT=raw))


def test_port_override_applies() -> None:
    settings = Settings.from_env(_env(MOCKSITE_SITE_PORT="18000", MOCKSITE_ADMIN_PORT="18001"))
    assert (settings.site_port, settings.admin_port) == (18000, 18001)


@pytest.mark.parametrize("level", ["debug", "WARNING", "critical"])
def test_log_levels_accepted(level: str) -> None:
    assert Settings.from_env(_env(MOCKSITE_LOG_LEVEL=level)).log_level == level.lower()


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(_env(MOCKSITE_LOG_LEVEL="verbose"))


def test_admin_dist_override() -> None:
    settings = Settings.from_env(_env(MOCKSITE_ADMIN_DIST="/srv/dist"))
    assert str(settings.admin_dist) == "/srv/dist"


def test_token_is_not_in_repr() -> None:
    settings = Settings.from_env(_env())
    assert GOOD_TOKEN not in repr(settings)
