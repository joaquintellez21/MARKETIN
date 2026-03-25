"""Bot configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _clean_private_key(raw: str) -> str:
    """Normalize a private key: strip whitespace, quotes, and 0x prefix."""
    key = raw.strip().strip("'\"")
    if key.startswith("0x") or key.startswith("0X"):
        key = key[2:]
    return key


@dataclass
class Config:
    # API credentials – traditional CLOB auth
    api_key: str = os.getenv("POLYMARKET_API_KEY", "")
    secret: str = os.getenv("POLYMARKET_SECRET", "")
    passphrase: str = os.getenv("POLYMARKET_PASSPHRASE", "")
    private_key: str = field(default_factory=lambda: _clean_private_key(os.getenv("PRIVATE_KEY", "")))

    # Alternative auth – for Gmail/Google (Privy) accounts
    # When secret & passphrase are empty, the bot will derive CLOB creds
    # automatically from the private key.
    derive_api_creds: bool = not os.getenv("POLYMARKET_SECRET", "").strip()

    # Chain
    chain_id: int = int(os.getenv("CHAIN_ID", "137"))

    # Trading
    max_position_size: float = float(os.getenv("MAX_POSITION_SIZE", "17"))
    stop_loss_percent: float = float(os.getenv("STOP_LOSS_PERCENT", "10"))
    take_profit_percent: float = float(os.getenv("TAKE_PROFIT_PERCENT", "20"))
    order_size: float = float(os.getenv("ORDER_SIZE", "5"))
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() == "true"

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # AI filter (Claude analysis before trading)
    claude_api_key: str = os.getenv("CLAUDE_API_KEY", "")
    use_ai_filter: bool = os.getenv("USE_AI_FILTER", "true").lower() == "true"
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "0.70"))

    # Strategy tuning
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "4"))
    scan_limit: int = int(os.getenv("SCAN_LIMIT", "100"))
    momentum_buy_below: float = float(os.getenv("MOMENTUM_BUY_BELOW", "0.45"))
    momentum_sell_above: float = float(os.getenv("MOMENTUM_SELL_ABOVE", "0.60"))
    momentum_min_volume: float = float(os.getenv("MOMENTUM_MIN_VOLUME", "1000"))
    momentum_max_spread: float = float(os.getenv("MOMENTUM_MAX_SPREAD", "0.08"))
    value_min_volume: float = float(os.getenv("VALUE_MIN_VOLUME", "2000"))
    value_max_price: float = float(os.getenv("VALUE_MAX_PRICE", "0.35"))
    value_max_spread: float = float(os.getenv("VALUE_MAX_SPREAD", "0.08"))

    # Weather strategy
    weather_min_edge: float = float(os.getenv("WEATHER_MIN_EDGE", "0.20"))
    weather_cities: list = field(
        default_factory=lambda: os.getenv("WEATHER_CITIES", "Chicago,New York,Los Angeles").split(",")
    )

    # Polling / WebSocket
    use_websocket: bool = os.getenv("USE_WEBSOCKET", "true").lower() == "true"
    poll_interval: int = int(os.getenv("POLL_INTERVAL", "15"))

    # API endpoints
    clob_api_url: str = "https://clob.polymarket.com"
    gamma_api_url: str = "https://gamma-api.polymarket.com"
