"""Main bot engine – orchestrates strategies, risk, and execution."""

import time
import signal
import sys

from config import Config
from client import PolymarketClient
from risk import RiskManager
from strategies import MomentumStrategy, MarketMakingStrategy, ValueStrategy, Strategy
from logger import setup_logger

logger = setup_logger("bot")


class PolymarketBot:
    """Core trading bot."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.client = PolymarketClient(self.config)
        self.risk = RiskManager(self.config)
        self.strategies: list[Strategy] = []
        self.running = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received, stopping bot...")
        self.running = False

    def add_strategy(self, strategy: Strategy):
        self.strategies.append(strategy)
        logger.info("Strategy added: %s", strategy.__class__.__name__)

    # ── Main Loop ─────────────────────────────────────────────────

    def run(self, interval: int = 60):
        """Run the bot with the given polling interval (seconds)."""
        logger.info("=" * 60)
        logger.info("Polymarket Trading Bot starting")
        logger.info("Dry run: %s", self.config.dry_run)
        logger.info("Strategies: %d", len(self.strategies))
        logger.info("Max position size: $%.2f", self.config.max_position_size)
        logger.info("=" * 60)

        self.running = True
        while self.running:
            try:
                self._tick()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error("Error in tick: %s", e, exc_info=True)

            logger.info("Sleeping %ds until next tick...", interval)
            time.sleep(interval)

        logger.info("Bot stopped.")
        self._print_summary()

    def _tick(self):
        """Single iteration: fetch markets, evaluate strategies, execute."""
        logger.info("─── Tick ───")

        # 1. Fetch markets
        markets = self.client.get_markets(limit=20)
        logger.info("Fetched %d markets", len(markets))

        # 2. Check existing positions for stop-loss / take-profit
        self._check_risk()

        # 3. Evaluate strategies on each market
        for market in markets:
            tokens = market.get("clobTokenIds") or market.get("tokens", [])
            if isinstance(tokens, str):
                tokens = [tokens]
            elif isinstance(tokens, list) and tokens and isinstance(tokens[0], dict):
                tokens = [t.get("token_id", t.get("tokenId", "")) for t in tokens]

            for token_id in tokens:
                if not token_id:
                    continue
                self._evaluate_market(token_id, market)

    def _evaluate_market(self, token_id: str, market_info: dict):
        """Run all strategies on a single token and execute signals."""
        for strategy in self.strategies:
            signals = strategy.evaluate(token_id, market_info)
            for sig in signals:
                self._execute_signal(token_id, sig, market_info)

    def _execute_signal(self, token_id: str, signal_data: dict, market_info: dict):
        """Execute a trade signal after risk checks."""
        action = signal_data["action"]
        price = signal_data["price"]
        size = signal_data["size"]
        reason = signal_data.get("reason", "")

        logger.info("Signal: %s %s %.2f @ $%.4f – %s", action, token_id[:12], size, price, reason)

        if action == "BUY":
            if not self.risk.can_open_position(size, price):
                return
            result = self.client.buy(token_id, price, size)
            if result is not None:
                self.risk.register_position(
                    token_id, "BUY", price, size,
                    market_name=market_info.get("question", ""),
                )

        elif action == "SELL":
            result = self.client.sell(token_id, price, size)
            if result is not None:
                self.risk.close_position(token_id)

    def _check_risk(self):
        """Check all positions for stop-loss and take-profit."""
        for token_id in list(self.risk.positions.keys()):
            try:
                mid = self.client.get_midpoint(token_id)
            except Exception:
                continue

            if self.risk.check_stop_loss(token_id, mid):
                pos = self.risk.positions[token_id]
                self.client.sell(token_id, mid, pos.size)
                self.risk.close_position(token_id)
            elif self.risk.check_take_profit(token_id, mid):
                pos = self.risk.positions[token_id]
                self.client.sell(token_id, mid, pos.size)
                self.risk.close_position(token_id)

    def _print_summary(self):
        summary = self.risk.get_portfolio_summary()
        logger.info("── Portfolio Summary ──")
        logger.info("Exposure: $%.2f / $%.2f", summary["total_exposure"], summary["max_allowed"])
        logger.info("Open positions: %d", summary["open_positions"])
        for tid, info in summary["positions"].items():
            logger.info("  %s: %s %.2f @ $%.4f (%s)", tid[:12], info["side"], info["size"], info["entry"], info["name"][:40])


def main():
    config = Config()
    bot = PolymarketBot(config)

    # Add default strategies
    bot.add_strategy(MomentumStrategy(bot.client, bot.risk))
    bot.add_strategy(MarketMakingStrategy(bot.client, bot.risk))
    bot.add_strategy(ValueStrategy(bot.client, bot.risk))

    bot.run(interval=60)


if __name__ == "__main__":
    main()
