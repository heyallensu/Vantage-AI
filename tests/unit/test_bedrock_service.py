"""Bedrock timeout, provider-error, and response-contract tests."""

import io
import json
from unittest.mock import Mock

import pytest
from botocore.config import Config
from botocore.exceptions import ClientError

from app.services.bedrock_service import (
    BedrockServiceError,
    analyze_records,
    ask_claude,
    build_bedrock_config,
    find_anomalies,
)


def bedrock_response(text: str) -> dict:
    return {"body": io.BytesIO(json.dumps({"content": [{"text": text}]}).encode())}


def test_bedrock_client_configuration_has_bounded_timeouts_and_retries() -> None:
    config = build_bedrock_config()

    assert isinstance(config, Config)
    assert config.connect_timeout == 3
    assert config.read_timeout == 15
    assert config.retries["total_max_attempts"] == 3


def test_analyze_records_validates_structured_model_output() -> None:
    client = Mock()
    client.invoke_model.return_value = bedrock_response(
        json.dumps(
            {
                "total_amount": 42.5,
                "record_count": 1,
                "top_categories": ["Operations"],
                "summary": "One financial operation was reviewed.",
                "anomalies": [],
            }
        )
    )

    result = analyze_records([{"amount": 42.5}], client=client)

    assert result["record_count"] == 1
    assert result["total_amount"] == 42.5


@pytest.mark.parametrize(
    "invalid_text",
    [
        "not-json",
        '{"record_count": "one"}',
        '{"total_amount": 1, "record_count": 1, "top_categories": [], '
        '"summary": "ok", "anomalies": [], "unexpected": true}',
    ],
)
def test_analyze_records_rejects_invalid_model_output(invalid_text: str) -> None:
    client = Mock()
    client.invoke_model.return_value = bedrock_response(invalid_text)

    with pytest.raises(BedrockServiceError, match="invalid response"):
        analyze_records([], client=client)


def test_find_anomalies_requires_a_string_array() -> None:
    client = Mock()
    client.invoke_model.return_value = bedrock_response('["valid", 123]')

    with pytest.raises(BedrockServiceError, match="invalid response"):
        find_anomalies([], client=client)


def test_provider_errors_are_converted_to_stable_service_error() -> None:
    client = Mock()
    client.invoke_model.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "provider detail"}},
        "InvokeModel",
    )

    with pytest.raises(BedrockServiceError, match="temporarily unavailable") as error:
        ask_claude("analyze", client=client)

    assert "provider detail" not in str(error.value)
