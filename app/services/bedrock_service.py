"""
Calls Amazon Bedrock Claude Haiku.
Used by the /insights endpoints to analyse records.
"""

import boto3
import json
import os
import re

bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"))

# Use inference profile for Claude Haiku 4.5 (required for non-ON_DEMAND models)
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "au.anthropic.claude-haiku-4-5-20251001-v1:0")


def _strip_markdown(text: str) -> str:
    """Strip ```json / ``` wrappers that Claude sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def ask_claude(prompt: str, max_tokens: int = 800) -> str:
    """Send a prompt to Claude Haiku and return the text response."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = bedrock.invoke_model(modelId=MODEL_ID, body=body)
    result   = json.loads(response["body"].read())
    return result["content"][0]["text"]


def analyze_records(records: list[dict]) -> dict:
    """
    Ask Claude to analyse a list of transaction records.
    Instructs Claude to return structured JSON only — no extra text.
    """
    records_text = json.dumps(records, indent=2)
    prompt = f"""You are a financial analyst.
Analyse these records and respond ONLY with valid JSON:
{{
  "total_amount": <float>,
  "record_count": <int>,
  "top_categories": ["<category>", ...],
  "summary": "<2-3 sentence plain English summary>",
  "anomalies": ["<anomaly description>", ...]
}}
Records:
{records_text}"""
    raw = ask_claude(prompt)
    return json.loads(_strip_markdown(raw))


def generate_summary(records: list[dict]) -> str:
    """Ask Claude for a plain English summary of the dataset."""
    records_text = json.dumps(records[:50], indent=2)  # limit to avoid token overflow
    prompt = f"""Summarise these business records in 3-4 sentences. Focus on patterns, totals, and anything unusual.
Records:
{records_text}"""
    return ask_claude(prompt, max_tokens=400)


def find_anomalies(records: list[dict]) -> list[str]:
    """Ask Claude to identify anomalous records."""
    records_text = json.dumps(records, indent=2)
    prompt = f"""You are an auditor. Identify any anomalous or suspicious records from this dataset.
Return ONLY a JSON array of strings, each describing one anomaly. Example: ["Unusually large amount on 2024-01-15", ...]
If there are no anomalies, return an empty array: []
Records:
{records_text}"""
    raw = ask_claude(prompt)
    return json.loads(_strip_markdown(raw))
