"""Main bot engine – orchestrates strategies, risk, and execution."""

import json
import os
import time
import signal
import sys

from config import Config
from client import PolymarketClient
from risk import RiskManager
from strategies import MomentumStrategy, MarketMakingStrategy, ValueStrategy, Strategy
from strategy_weather import WeatherStrategy
from ai_filter import analyze_trade
from ws_feed import MarketFeed
from dashboard import Dashboard
from logger import setup_logger

logger = setup_logger("bot")

POSITIONS_FILE = "positions.json"


class PolymarketBot:
    """Core trading bot."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.client = PolymarketClient(self.config)
        self.risk = RiskManager(self.config)
        self.strategies: list[Strategy] = []
        self.running = False
        self.dashboard = Dashboard(self.config)
        self._ws_feed: MarketFeed | None = None
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

    def run(self, interval: int = 15):
        """Run the bot with the given polling interval (seconds)."""
        interval = self.config.poll_interval
        logger.info("Polymarket Trading Bot starting (interval=%ds)", interval)

        self._load_positions()
        self.running = True

        # Start WebSocket feed if enabled
        if self.config.use_websocket:
            self._ws_feed = MarketFeed()
            self._ws_feed.start()
            self.dashboard.log_info("WebSocket feed iniciado")

        ai_status = "AI ON" if (self.config.use_ai_filter and self.config.claude_api_key) else "AI OFF"
        ws_status = "WS" if self.config.use_websocket else f"Poll {interval}s"
        self.dashboard.log_info(
            f"Bot iniciado | {len(self.strategies)} estrategias | "
            f"{'DRY RUN' if self.config.dry_run else 'LIVE'} | {ai_status} | {ws_status}"
        )

        self.dashboard.start()
        try:
            while self.running:
                try:
                    self.client.clear_cache()
                    tick_start = time.monotonic()
                    self._tick()
                    self.dashboard.last_tick_time = time.monotonic() - tick_start
                    self.dashboard.tick_count += 1
                    self._save_positions()
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error("Error in tick: %s", e, exc_info=True)
                    self.dashboard.log_error(str(e)[:60])

                # Countdown between ticks with live UI updates
                for remaining in range(interval, 0, -1):
                    if not self.running:
                        break
                    self.dashboard.update(self.risk, self._safe_midpoint)
                    time.sleep(1)
        finally:
            if self._ws_feed:
                self._ws_feed.stop()
            self.dashboard.stop()

        logger.info("Bot stopped.")
        self._save_positions()
        self._print_summary()

    def _safe_midpoint(self, token_id: str) -> float:
        """Get midpoint without raising (for dashboard display)."""
        try:
            return self.client.get_midpoint(token_id)
        except Exception:
            pos = self.risk.positions.get(token_id)
            return pos.entry_price if pos else 0.0

    def _tick(self):
        """Single iteration: fetch markets, evaluate strategies, execute."""
        # 1. Fetch markets
        markets = self.client.get_markets(limit=50)
        self.dashboard.markets_scanned = len(markets)
        self.dashboard.log_info(f"Escaneando {len(markets)} mercados...")

        # Track cache hits for stats
        calls_before = len(self.client._book_cache)

        # 2. Check existing positions for stop-loss / take-profit
        self._check_risk()

        # 3. Evaluate strategies on each market
        for market in markets:
            tokens = market.get("clobTokenIds") or market.get("tokens", [])

            if isinstance(tokens, str):
                try:
                    tokens = json.loads(tokens)
                except (json.JSONDecodeError, TypeError):
                    tokens = [tokens]

            if isinstance(tokens, list) and tokens and isinstance(tokens[0], dict):
                tokens = [t.get("token_id", t.get("tokenId", "")) for t in tokens]

            for token_id in tokens:
                if not token_id:
                    continue
                self._evaluate_market(token_id, market)

        # Update cache savings stat
        calls_after = len(self.client._book_cache)
        self.dashboard.api_calls_saved += max(0, calls_after - calls_before)

        # Update dashboard
        self.dashboard.update(self.risk, self._safe_midpoint)

    def _evaluate_market(self, token_id: str, market_info: dict):
        """Run all strategies on a single token and execute signals."""
        for strategy in self.strategies:
            signals = strategy.evaluate(token_id, market_info)
            for sig in signals:
                self._execute_signal(token_id, sig, market_info)

    def _execute_signal(self, token_id: str, signal_data: dict, market_info: dict):
        """Execute a trade signal after risk checks and AI validation."""
        action = signal_data["action"]
        price = signal_data["price"]
        size = signal_data["size"]
        reason = signal_data.get("reason", "")

        self.dashboard.log_signal(action, token_id, price, reason)
        logger.info("Signal: %s %s %.2f @ $%.4f - %s", action, token_id[:12], size, price, reason)

        try:
            if action == "BUY":
                if not self.risk.can_open_position(size, price):
                    self.dashboard.log_rejected(
                        f"Exposicion ${self.risk.total_exposure:.2f} + ${size * price:.2f} > max ${self.config.max_position_size:.2f}"
                    )
                    return

                # AI filter – ask Claude before executing BUY
                volume = float(market_info.get("volume", 0) or 0)
                try:
                    price_data = self.client.get_price(token_id)
                    spread = price_data["spread"]
                except Exception:
                    spread = 0.0

                ai_result = analyze_trade(
                    self.config,
                    market_name=market_info.get("question", "Unknown"),
                    action=action,
                    price=price,
                    volume=volume,
                    spread=spread,
                    reason=reason,
                )

                if ai_result["confidence"] < self.config.min_confidence:
                    self.dashboard.log_rejected(
                        f"AI: conf {ai_result['confidence']:.0%} < {self.config.min_confidence:.0%} | {ai_result['reasoning'][:40]}"
                    )
                    logger.info(
                        "AI filter rejected %s: confidence=%.2f, reason=%s",
                        token_id[:12], ai_result["confidence"], ai_result["reasoning"],
                    )
                    return

                if ai_result["recommendation"] == "SKIP":
                    self.dashboard.log_rejected(f"AI: SKIP | {ai_result['reasoning'][:50]}")
                    logger.info("AI filter SKIP for %s: %s", token_id[:12], ai_result["reasoning"])
                    return

                result = self.client.buy(token_id, price, size)
                if result is not None:
                    self.risk.register_position(
                        token_id, "BUY", price, size,
                        market_name=market_info.get("question", ""),
                    )
                    self.dashboard.log_trade("BUY", token_id, price, size)

            elif action == "SELL":
                result = self.client.sell(token_id, price, size)
                if result is not None:
                    self.risk.close_position(token_id)
                    self.dashboard.log_trade("SELL", token_id, price, size)

        except Exception as e:
            logger.warning("Order failed for %s: %s", token_id[:12], e)
            self.dashboard.log_error(f"Order failed: {e}"[:55])

    def _check_risk(self):
        """Check all positions for stop-loss and take-profit."""
        for token_id in list(self.risk.positions.keys()):
            try:
                mid = self.client.get_midpoint(token_id)
            except Exception:
                continue

            pos = self.risk.positions[token_id]

            if self.risk.check_stop_loss(token_id, mid):
                loss_pct = ((pos.entry_price - mid) / pos.entry_price) * 100
                self.dashboard.log_stop_loss(token_id, loss_pct)
                self.client.sell(token_id, mid, pos.size)
                self.risk.close_position(token_id)
                self.dashboard.log_trade("SELL", token_id, mid, pos.size)

            elif self.risk.check_take_profit(token_id, mid):
                gain_pct = ((mid - pos.entry_price) / pos.entry_price) * 100
                self.dashboard.log_take_profit(token_id, gain_pct)
                self.client.sell(token_id, mid, pos.size)
                self.risk.close_position(token_id)
                self.dashboard.log_trade("SELL", token_id, mid, pos.size)

    # ── Position Persistence ──────────────────────────────────────

    def _save_positions(self):
        """Save open positions to disk so they survive restarts."""
        data = {}
        for tid, pos in self.risk.positions.items():
            data[tid] = {
                "side": pos.side,
                "entry_price": pos.entry_price,
                "size": pos.size,
                "market_name": pos.market_name,
            }
        try:
            with open(POSITIONS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save positions: %s", e)

    def _load_positions(self):
        """Load positions from disk on startup."""
        if not os.path.exists(POSITIONS_FILE):
            return
        try:
            with open(POSITIONS_FILE) as f:
                data = json.load(f)
            from risk import Position
            for tid, info in data.items():
                pos = Position(
                    token_id=tid,
                    side=info["side"],
                    entry_price=info["entry_price"],
                    size=info["size"],
                    market_name=info.get("market_name", ""),
                )
                self.risk.positions[tid] = pos
                self.risk.total_exposure += pos.size * pos.entry_price
            if data:
                self.dashboard.log_info(
                    f"Cargadas {len(data)} posiciones (${self.risk.total_exposure:.2f})"
                )
            logger.info("Loaded %d positions from disk (exposure: $%.2f)",
                        len(data), self.risk.total_exposure)
        except Exception as e:
            logger.warning("Failed to load positions: %s", e)

    def _print_summary(self):
        summary = self.risk.get_portfolio_summary()
        logger.info("-- Portfolio Summary --")
        logger.info("Exposure: $%.2f / $%.2f", summary["total_exposure"], summary["max_allowed"])
        logger.info("Open positions: %d", summary["open_positions"])
        for tid, info in summary["positions"].items():
            logger.info("  %s: %s %.2f @ $%.4f (%s)", tid[:12], info["side"], info["size"], info["entry"], info["name"][:40])


def main():
    config = Config()
    bot = PolymarketBot(config)

    # Add strategies based on balance size
    bot.add_strategy(MomentumStrategy(bot.client, bot.risk))
    bot.add_strategy(ValueStrategy(bot.client, bot.risk))
    if config.max_position_size >= 50:
        bot.add_strategy(MarketMakingStrategy(bot.client, bot.risk))

    # Weather strategy – uses NOAA public forecasts
    bot.add_strategy(WeatherStrategy(
        bot.client, bot.risk,
        min_edge=config.weather_min_edge,
        cities=[c.strip() for c in config.weather_cities],
    ))

    bot.run(interval=config.poll_interval)


if __name__ == "__main__":
    main()
