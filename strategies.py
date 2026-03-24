"""Trading strategies for Polymarket."""

from abc import ABC, abstractmethod

from client import PolymarketClient
from risk import RiskManager
from logger import setup_logger

logger = setup_logger("strategies")


class Strategy(ABC):
    """Base class for trading strategies."""

    def __init__(self, client: PolymarketClient, risk: RiskManager):
        self.client = client
        self.risk = risk

    @abstractmethod
    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        """Evaluate the market and return a list of trade signals.

        Each signal: {"action": "BUY"|"SELL", "price": float, "size": float, "reason": str}
        """


class MomentumStrategy(Strategy):
    """Buy tokens trending upward below a threshold; sell when above."""

    def __init__(self, client: PolymarketClient, risk: RiskManager,
                 buy_below: float = 0.40, sell_above: float = 0.75):
        super().__init__(client, risk)
        self.buy_below = buy_below
        self.sell_above = sell_above

    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        signals = []
        try:
            price_data = self.client.get_price(token_id)
            mid = (price_data["bid"] + price_data["ask"]) / 2
        except Exception as e:
            logger.error("Failed to get price for %s: %s", token_id[:12], e)
            return signals

        if mid < self.buy_below and price_data["spread"] < 0.10:
            signals.append({
                "action": "BUY",
                "price": price_data["ask"],
                "size": self.client.config.order_size,
                "reason": f"Momentum: price ${mid:.4f} < buy_below ${self.buy_below}",
            })

        if mid > self.sell_above and token_id in self.risk.positions:
            pos = self.risk.positions[token_id]
            signals.append({
                "action": "SELL",
                "price": price_data["bid"],
                "size": pos.size,
                "reason": f"Momentum: price ${mid:.4f} > sell_above ${self.sell_above}",
            })

        return signals


class MarketMakingStrategy(Strategy):
    """Place buy and sell orders around the midpoint to capture the spread."""

    def __init__(self, client: PolymarketClient, risk: RiskManager,
                 spread_offset: float = 0.02, min_spread: float = 0.03):
        super().__init__(client, risk)
        self.spread_offset = spread_offset
        self.min_spread = min_spread

    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        signals = []
        try:
            price_data = self.client.get_price(token_id)
        except Exception as e:
            logger.error("Failed to get price for %s: %s", token_id[:12], e)
            return signals

        if price_data["spread"] < self.min_spread:
            logger.debug("Spread too tight (%.4f) for %s, skipping", price_data["spread"], token_id[:12])
            return signals

        mid = (price_data["bid"] + price_data["ask"]) / 2
        buy_price = round(mid - self.spread_offset, 4)
        sell_price = round(mid + self.spread_offset, 4)

        if 0.01 <= buy_price <= 0.99:
            signals.append({
                "action": "BUY",
                "price": buy_price,
                "size": self.client.config.order_size,
                "reason": f"MM: bid at ${buy_price:.4f} (mid ${mid:.4f})",
            })

        if 0.01 <= sell_price <= 0.99:
            signals.append({
                "action": "SELL",
                "price": sell_price,
                "size": self.client.config.order_size,
                "reason": f"MM: ask at ${sell_price:.4f} (mid ${mid:.4f})",
            })

        return signals


class ValueStrategy(Strategy):
    """Buy markets that appear mispriced based on a simple threshold analysis."""

    def __init__(self, client: PolymarketClient, risk: RiskManager,
                 min_volume: float = 1000, max_price: float = 0.30):
        super().__init__(client, risk)
        self.min_volume = min_volume
        self.max_price = max_price

    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        signals = []
        volume = float(market_info.get("volume", 0) or 0)
        if volume < self.min_volume:
            return signals

        try:
            price_data = self.client.get_price(token_id)
            mid = (price_data["bid"] + price_data["ask"]) / 2
        except Exception as e:
            logger.error("Failed to get price for %s: %s", token_id[:12], e)
            return signals

        if mid <= self.max_price and price_data["spread"] < 0.08:
            signals.append({
                "action": "BUY",
                "price": price_data["ask"],
                "size": self.client.config.order_size,
                "reason": f"Value: low price ${mid:.4f}, volume ${volume:.0f}",
            })

        return signals
