"""Market scanner – discover and filter interesting markets."""

import requests
from config import Config
from logger import setup_logger

logger = setup_logger("scanner")


class MarketScanner:
    """Scans Polymarket for markets matching certain criteria."""

    def __init__(self, config: Config):
        self.config = config

    def fetch_all_markets(self, limit: int = 100) -> list[dict]:
        """Fetch active markets from the Gamma API."""
        resp = requests.get(
            f"{self.config.gamma_api_url}/markets",
            params={"limit": limit, "active": True, "closed": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def filter_by_volume(self, markets: list[dict], min_volume: float = 5000) -> list[dict]:
        """Keep only markets with sufficient volume."""
        return [m for m in markets if float(m.get("volume", 0) or 0) >= min_volume]

    def filter_by_liquidity(self, markets: list[dict], min_liquidity: float = 1000) -> list[dict]:
        """Keep only markets with sufficient liquidity."""
        return [m for m in markets if float(m.get("liquidity", 0) or 0) >= min_liquidity]

    def scan(self, min_volume: float = 5000, min_liquidity: float = 1000) -> list[dict]:
        """Fetch and filter markets."""
        markets = self.fetch_all_markets()
        markets = self.filter_by_volume(markets, min_volume)
        markets = self.filter_by_liquidity(markets, min_liquidity)

        logger.info("Scanner found %d markets (vol >= $%.0f, liq >= $%.0f)",
                     len(markets), min_volume, min_liquidity)

        for m in markets[:5]:
            logger.info("  → %s | vol: $%s | liq: $%s",
                        m.get("question", "?")[:60],
                        m.get("volume", "?"),
                        m.get("liquidity", "?"))

        return markets
