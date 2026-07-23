"""Phase 0 spike: prove the Cerebras structured-output round-trip.

Runs one hardcoded prompt through LiteLLM -> OpenRouter -> gpt-oss-120b on
Cerebras with a Pydantic response schema, and parses the result back into an
object. This de-risks the core generation path before Phase 4 builds on it.

Run: uv run python spike_cerebras.py  (from the backend/ directory)
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


class ListingBlurb(BaseModel):
    """Minimal structured output to validate the round-trip."""

    headline: str
    caption: str


def run() -> ListingBlurb:
    messages = [
        {
            "role": "user",
            "content": (
                "Write a one-line Instagram headline and a short caption for a "
                "beachfront luxury villa in Maui with an infinity pool."
            ),
        }
    ]
    response = completion(
        model=MODEL,
        messages=messages,
        response_format=ListingBlurb,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    result = response.choices[0].message.content
    return ListingBlurb.model_validate_json(result)


if __name__ == "__main__":
    blurb = run()
    print("Parsed structured output:")
    print(f"  headline: {blurb.headline}")
    print(f"  caption:  {blurb.caption}")
