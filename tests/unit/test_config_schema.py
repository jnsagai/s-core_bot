"""Every config fixture in tests/fixtures/config/ produces the expected dotted error path and
reason (or, for the two valid fixtures, loads cleanly)."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.config.loader import load_config
from score_docs_assistant.domain.errors import ConfigError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "config"


def _load(name: str):
    return load_config(config_path=FIXTURES / name, env={}, cwd=FIXTURES)


@pytest.mark.parametrize(
    ("fixture", "expected_path"),
    [
        ("unknown_top_level_key.yaml", "telemtry_typo"),
        ("unknown_nested_key.yaml", "server.hots"),
        ("wrong_type.yaml", "server.port"),
        ("out_of_range_port.yaml", "server.port"),
        ("host_wildcard.yaml", "server.host"),
        ("host_lan_ip.yaml", "server.host"),
        ("host_hostname.yaml", "server.host"),
        ("base_url_off_host.yaml", "runtime.base_url"),
        ("base_url_https.yaml", "runtime.base_url"),
        ("base_url_userinfo.yaml", "runtime.base_url"),
        ("cloud_fallback_true.yaml", "runtime.cloud_fallback"),
        ("provider_openai.yaml", "runtime.provider"),
        ("telemetry_true.yaml", "privacy.telemetry"),
        ("profile_public.yaml", "profile"),
    ],
)
def test_invalid_fixture_reports_dotted_path_and_reason(fixture: str, expected_path: str) -> None:
    with pytest.raises(ConfigError) as exc_info:
        _load(fixture)
    paths = [path for path, _reason in exc_info.value.errors]
    assert any(p == expected_path or p.startswith(f"{expected_path}.") for p in paths), paths
    for _path, reason in exc_info.value.errors:
        assert reason, "every error must carry a non-empty reason"


def test_invalid_yaml_reports_config_file_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        _load("invalid_yaml.yaml")
    assert exc_info.value.errors[0][0] == "config_file"


def test_valid_fixture_loads_cleanly() -> None:
    effective = _load("valid.yaml")
    assert effective.config.server.port == 9090
    assert effective.sources["server.port"] == "file"
    assert effective.sources["server.allowed_hosts"] == "default"


def test_ipv6_loopback_host_is_valid() -> None:
    effective = _load("host_ipv6_loopback_valid.yaml")
    assert effective.config.server.host == "::1"
