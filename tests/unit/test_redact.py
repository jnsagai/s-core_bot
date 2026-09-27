"""No fixture secret survives redaction: URL userinfo, secret-named keys, nested dicts, and
free-text key=value fragments (FR-008, SC-006)."""

from __future__ import annotations

from score_docs_assistant.config.redact import redact_mapping, redact_text, redact_url

SECRET_VALUE = "sk-super-secret-value-12345"


def test_redact_url_strips_userinfo() -> None:
    result = redact_url(f"http://user:{SECRET_VALUE}@127.0.0.1:11434")
    assert SECRET_VALUE not in result
    assert result == "http://***@127.0.0.1:11434"


def test_redact_text_masks_key_value_fragments() -> None:
    for text in (
        f"api_key={SECRET_VALUE}",
        f"API-KEY: {SECRET_VALUE}",
        f"password={SECRET_VALUE}",
        f"Authorization: Bearer {SECRET_VALUE}",
    ):
        result = redact_text(text)
        assert SECRET_VALUE not in result, text


def test_redact_mapping_masks_secret_named_keys() -> None:
    data = {"token": SECRET_VALUE, "server": {"api_key": SECRET_VALUE, "port": 8080}}
    result = redact_mapping(data)
    assert result["token"] == "***"
    assert result["server"]["api_key"] == "***"
    assert result["server"]["port"] == 8080


def test_redact_mapping_handles_nested_lists_and_urls() -> None:
    data = {
        "runtime": {
            "base_url": f"http://user:{SECRET_VALUE}@127.0.0.1:11434",
            "history": [f"password={SECRET_VALUE}", {"credential": SECRET_VALUE}],
        }
    }
    result = redact_mapping(data)
    dumped = str(result)
    assert SECRET_VALUE not in dumped


def test_redact_mapping_leaves_non_secret_values_untouched() -> None:
    data = {"server": {"host": "127.0.0.1", "port": 8080}}
    assert redact_mapping(data) == data
