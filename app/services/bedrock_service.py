"""Validated, bounded Amazon Bedrock service boundary."""

import json
import re
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.core.config import get_settings


class BedrockServiceError(RuntimeError):
    """Stable application error that does not expose provider details."""


class AnalysisResult(BaseModel):
    """Exact response contract expected from the financial analysis prompt."""

    model_config = ConfigDict(extra="forbid", strict=True)

    total_amount: float
    record_count: int
    top_categories: list[str]
    summary: str = Field(min_length=1)
    anomalies: list[str]


ANOMALY_LIST = TypeAdapter(list[str], config=ConfigDict(strict=True))


def build_bedrock_config() -> Config:
    """Use bounded network operations and a small provider retry budget."""
    return Config(
        connect_timeout=3,
        read_timeout=15,
        retries={"mode": "standard", "total_max_attempts": 3},
    )


@lru_cache
def get_bedrock_client():
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=build_bedrock_config(),
    )


def _strip_markdown(text: str) -> str:
    """Strip fenced JSON wrappers that a model can add despite the prompt."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def ask_claude(
    prompt: str,
    max_tokens: int = 800,
    *,
    client=None,
) -> str:
    """Invoke the configured model and normalize provider failures."""
    settings = get_settings()
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    try:
        response = (client or get_bedrock_client()).invoke_model(
            modelId=settings.bedrock_model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        if not isinstance(text, str) or not text.strip():
            raise TypeError("Model response text is empty")
        return text
    except (BotoCoreError, ClientError) as exc:
        raise BedrockServiceError("AI analysis is temporarily unavailable") from exc
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise BedrockServiceError("AI provider returned an invalid response") from exc


def analyze_records(records: list[dict], *, client=None) -> dict:
    """Analyze financial operations and enforce the exact JSON response schema."""
    records_text = json.dumps(records[:200], separators=(",", ":"))
    prompt = f"""You are a financial operations analyst.
Review the supplied transaction records. Respond ONLY with valid JSON matching this schema:
{{
  "total_amount": <float>,
  "record_count": <integer>,
  "top_categories": ["<category>"],
  "summary": "<concise business summary>",
  "anomalies": ["<specific anomaly>"]
}}
Do not provide financial advice. Report only observations supported by the records.
Records:
{records_text}"""
    raw = ask_claude(prompt, client=client)
    try:
        result = AnalysisResult.model_validate_json(_strip_markdown(raw))
    except ValidationError as exc:
        raise BedrockServiceError("AI provider returned an invalid response") from exc
    return result.model_dump()


def generate_summary(records: list[dict], *, client=None) -> str:
    """Generate a concise descriptive summary, bounded to the first 50 records."""
    records_text = json.dumps(records[:50], separators=(",", ":"))
    prompt = f"""Summarize these financial operations in 3-4 sentences.
Describe totals, patterns, and unusual entries. Do not provide financial advice.
Records:
{records_text}"""
    return ask_claude(prompt, max_tokens=400, client=client)


def find_anomalies(records: list[dict], *, client=None) -> list[str]:
    """Identify record-level anomalies and enforce a strict string-array result."""
    records_text = json.dumps(records[:200], separators=(",", ":"))
    prompt = f"""Act as a financial operations auditor.
Return ONLY a JSON array of strings describing anomalies supported by these records.
Return [] when no anomaly is supported. Do not provide financial advice.
Records:
{records_text}"""
    raw = ask_claude(prompt, client=client)
    try:
        return ANOMALY_LIST.validate_json(_strip_markdown(raw))
    except ValidationError as exc:
        raise BedrockServiceError("AI provider returned an invalid response") from exc
