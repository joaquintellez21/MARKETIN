"""AI filter – asks Claude to validate trade signals before execution.

Uses Claude Haiku (claude-haiku-4-5-20251001) to keep costs minimal (~$0.001 per call).
Can be disabled via USE_AI_FILTER=false in .env.
"""

import json

from config import Config
from logger import setup_logger

logger = setup_logger("ai_filter")

# Lazy-load anthropic to avoid import errors when AI filter is disabled
_anthropic_client = None


def _get_client(api_key: str):
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def analyze_trade(
    config: Config,
    market_name: str,
    action: str,
    price: float,
    volume: float,
    spread: float,
    reason: str,
) -> dict:
    """Ask Claude to evaluate a trade signal.

    Returns:
        {"confidence": float, "recommendation": "BUY"|"SKIP", "reasoning": str}

    If the AI filter is disabled or fails, returns a pass-through approval.
    """
    # Bypass if disabled or no API key
    if not config.use_ai_filter or not config.claude_api_key:
        return {"confidence": 1.0, "recommendation": action, "reasoning": "AI filter disabled"}

    prompt = (
        f"You are a quantitative trading analyst for prediction markets. "
        f"Evaluate this trade signal and respond ONLY with valid JSON.\n\n"
        f"Market: {market_name}\n"
        f"Signal: {action}\n"
        f"Current price: {price:.4f}\n"
        f"Volume (USD): {volume:.0f}\n"
        f"Bid-ask spread: {spread:.4f}\n"
        f"Strategy reason: {reason}\n\n"
        f"Respond with this exact JSON format, nothing else:\n"
        f'{{"confidence": 0.0 to 1.0, "recommendation": "BUY" or "SKIP", "reasoning": "one sentence"}}'
    )

    try:
        client = _get_client(config.claude_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Parse JSON from response (handle potential markdown wrapping)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        # Validate structure
        confidence = float(result.get("confidence", 0))
        recommendation = result.get("recommendation", "SKIP")
        reasoning = result.get("reasoning", "")

        logger.info(
            "AI filter: %s | confidence=%.2f | rec=%s | %s",
            market_name[:40], confidence, recommendation, reasoning[:60],
        )

        return {
            "confidence": confidence,
            "recommendation": recommendation,
            "reasoning": reasoning,
        }

    except json.JSONDecodeError as e:
        logger.warning("AI filter: invalid JSON response: %s", e)
        return {"confidence": 0.0, "recommendation": "SKIP", "reasoning": "JSON parse error"}
    except Exception as e:
        logger.warning("AI filter error (passing through): %s", e)
        # On error, allow the trade to proceed (fail-open)
        return {"confidence": 1.0, "recommendation": action, "reasoning": f"AI filter error: {e}"}
