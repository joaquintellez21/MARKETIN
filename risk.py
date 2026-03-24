"""Risk management module."""

from dataclasses import dataclass, field

from config import Config
from logger import setup_logger

logger = setup_logger("risk")


@dataclass
class Position:
    token_id: str
    side: str
    entry_price: float
    size: float
    market_name: str = ""


class RiskManager:
    """Enforces position sizing, stop-loss, and take-profit rules."""

    def __init__(self, config: Config):
        self.config = config
        self.positions: dict[str, Position] = {}
        self.total_exposure: float = 0.0

    def can_open_position(self, size: float, price: float) -> bool:
        """Check if a new position fits within risk limits."""
        cost = size * price
        if self.total_exposure + cost > self.config.max_position_size:
            logger.warning(
                "Position rejected: exposure $%.2f + $%.2f > max $%.2f",
                self.total_exposure, cost, self.config.max_position_size,
            )
            return False
        return True

    def register_position(self, token_id: str, side: str, price: float, size: float, market_name: str = ""):
        cost = size * price
        self.positions[token_id] = Position(token_id, side, price, size, market_name)
        self.total_exposure += cost
        logger.info("Position registered: %s %s %.2f @ $%.4f (exposure: $%.2f)", side, token_id[:12], size, price, self.total_exposure)

    def check_stop_loss(self, token_id: str, current_price: float) -> bool:
        """Returns True if position should be closed (stop-loss triggered)."""
        pos = self.positions.get(token_id)
        if not pos:
            return False

        if pos.side == "BUY":
            loss_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
        else:
            loss_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100

        if loss_pct >= self.config.stop_loss_percent:
            logger.warning("STOP LOSS triggered for %s: loss %.2f%%", token_id[:12], loss_pct)
            return True
        return False

    def check_take_profit(self, token_id: str, current_price: float) -> bool:
        """Returns True if position should be closed (take-profit triggered)."""
        pos = self.positions.get(token_id)
        if not pos:
            return False

        if pos.side == "BUY":
            gain_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        else:
            gain_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100

        if gain_pct >= self.config.take_profit_percent:
            logger.info("TAKE PROFIT triggered for %s: gain %.2f%%", token_id[:12], gain_pct)
            return True
        return False

    def close_position(self, token_id: str):
        pos = self.positions.pop(token_id, None)
        if pos:
            self.total_exposure -= pos.size * pos.entry_price
            logger.info("Position closed: %s (exposure: $%.2f)", token_id[:12], self.total_exposure)

    def get_portfolio_summary(self) -> dict:
        return {
            "total_exposure": self.total_exposure,
            "max_allowed": self.config.max_position_size,
            "open_positions": len(self.positions),
            "positions": {
                tid: {
                    "side": p.side,
                    "entry": p.entry_price,
                    "size": p.size,
                    "name": p.market_name,
                }
                for tid, p in self.positions.items()
            },
        }
