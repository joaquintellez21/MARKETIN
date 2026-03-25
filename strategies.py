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
    """Buy tokens with low price and decent volume; sell when target is hit."""

    def __init__(self, client: PolymarketClient, risk: RiskManager,
                 buy_below: float = 0.45, sell_above: float = 0.60,
                 min_volume: float = 1000, max_spread: float = 0.08,
                 max_positions: int = 4):
        super().__init__(client, risk)
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.min_volume = min_volume
        self.max_spread = max_spread
        self.max_positions = max_positions

    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        signals = []
        market_name = market_info.get("question", "Unknown")

        # Skip if we already have too many open positions
        if len(self.risk.positions) >= self.max_positions and token_id not in self.risk.positions:
            return signals

        # Require minimum volume for safety
        volume = float(market_info.get("volume", 0) or 0)
        if volume < self.min_volume:
            return signals

        try:
            price_data = self.client.get_price(token_id)
            mid = (price_data["bid"] + price_data["ask"]) / 2
        except Exception as e:
            logger.error("Failed to get price for %s: %s", token_id[:12], e)
            return signals

        # Skip wide spreads (illiquid markets)
        if price_data["spread"] > self.max_spread:
            return signals

        # BUY: cheap token with tight spread in active market
        if mid < self.buy_below and token_id not in self.risk.positions:
            signals.append({
                "action": "BUY",
                "price": price_data["ask"],
                "size": self.client.config.order_size,
                "reason": f"Momentum: {market_name[:50]} @ ${mid:.4f} (vol ${volume:.0f})",
            })

        # SELL: price rose above target
        if mid > self.sell_above and token_id in self.risk.positions:
            pos = self.risk.positions[token_id]
            signals.append({
                "action": "SELL",
                "price": price_data["bid"],
                "size": pos.size,
                "reason": f"Momentum SELL: {market_name[:50]} @ ${mid:.4f}",
            })

        return signals


class MarketMakingStrategy(Strategy):
    """Place buy and sell orders around the midpoint to capture the spread.

    NOTE: Requires significant capital to be effective. Not recommended
    for balances under $50.
    """

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
    """Buy high-volume markets with very low prices (potential undervaluation)."""

    def __init__(self, client: PolymarketClient, risk: RiskManager,
                 min_volume: float = 2000, max_price: float = 0.35,
                 max_spread: float = 0.08, max_positions: int = 4):
        super().__init__(client, risk)
        self.min_volume = min_volume
        self.max_price = max_price
        self.max_spread = max_spread
        self.max_positions = max_positions

    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        signals = []
        market_name = market_info.get("question", "Unknown")

        # Skip if we already have too many open positions
        if len(self.risk.positions) >= self.max_positions and token_id not in self.risk.positions:
            return signals

        volume = float(market_info.get("volume", 0) or 0)
        if volume < self.min_volume:
            return signals

        try:
            price_data = self.client.get_price(token_id)
            mid = (price_data["bid"] + price_data["ask"]) / 2
        except Exception as e:
            logger.error("Failed to get price for %s: %s", token_id[:12], e)
            return signals

        # Only buy if spread is tight (liquid market)
        if price_data["spread"] > self.max_spread:
            return signals

        if mid <= self.max_price and token_id not in self.risk.positions:
            signals.append({
                "action": "BUY",
                "price": price_data["ask"],
                "size": self.client.config.order_size,
                "reason": f"Value: {market_name[:50]} @ ${mid:.4f} (vol ${volume:.0f})",
            })

        return signals
