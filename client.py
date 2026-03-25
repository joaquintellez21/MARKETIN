"""Polymarket API client wrapper."""

import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from config import Config
from logger import setup_logger

logger = setup_logger("client")


class PolymarketClient:
    """Wrapper around the Polymarket CLOB client."""

    def __init__(self, config: Config):
        self.config = config

        if config.derive_api_creds:
            # Gmail/Google (Privy) accounts: derive CLOB creds from private key
            logger.info("No secret/passphrase found – deriving API credentials from private key...")
            self.client = ClobClient(
                config.clob_api_url,
                key=config.private_key,
                chain_id=config.chain_id,
            )
            try:
                creds = self.client.derive_api_key()
                logger.info("API credentials derived successfully")
            except Exception:
                logger.info("No existing creds, creating new API key...")
                creds = self.client.create_api_key()
                logger.info("API credentials created successfully")

            self.client.set_api_creds(creds)
        else:
            # Traditional CLOB auth with API Key + Secret + Passphrase
            self.client = ClobClient(
                config.clob_api_url,
                key=config.private_key,
                chain_id=config.chain_id,
                creds={
                    "apiKey": config.api_key,
                    "secret": config.secret,
                    "passphrase": config.passphrase,
                },
            )

        logger.info("Polymarket client initialized (dry_run=%s)", config.dry_run)

    # ── Market Data ───────────────────────────────────────────────

    def get_markets(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Fetch active markets from the Gamma API."""
        resp = requests.get(
            f"{self.config.gamma_api_url}/markets",
            params={"limit": limit, "offset": offset, "active": True, "closed": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_market(self, condition_id: str) -> dict:
        """Get a single market by condition ID."""
        resp = requests.get(
            f"{self.config.gamma_api_url}/markets/{condition_id}",
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_orderbook(self, token_id: str) -> dict:
        """Get the order book for a token."""
        return self.client.get_order_book(token_id)

    def get_midpoint(self, token_id: str) -> float:
        """Get the midpoint price for a token."""
        book = self.get_orderbook(token_id)
        best_bid = float(book.bids[0].price) if book.bids else 0.0
        best_ask = float(book.asks[0].price) if book.asks else 1.0
        return (best_bid + best_ask) / 2

    def get_price(self, token_id: str) -> dict:
        """Get best bid/ask for a token."""
        book = self.get_orderbook(token_id)
        return {
            "bid": float(book.bids[0].price) if book.bids else 0.0,
            "ask": float(book.asks[0].price) if book.asks else 1.0,
            "spread": (
                float(book.asks[0].price) - float(book.bids[0].price)
                if book.asks and book.bids
                else 1.0
            ),
        }

    # ── Orders ────────────────────────────────────────────────────

    def create_order(
        self, token_id: str, side: str, price: float, size: float
    ) -> dict | None:
        """Create a limit order. Returns order response or None in dry-run."""
        side_val = BUY if side.upper() == "BUY" else SELL

        order_args = OrderArgs(
            price=price,
            size=size,
            side=side_val,
            token_id=token_id,
        )

        signed_order = self.client.create_order(order_args)

        if self.config.dry_run:
            logger.info(
                "[DRY RUN] Order: %s %.2f @ $%.4f on %s",
                side, size, price, token_id[:12],
            )
            return {"dry_run": True, "order": str(signed_order)}

        resp = self.client.post_order(signed_order, OrderType.GTC)
        logger.info(
            "Order placed: %s %.2f @ $%.4f on %s → %s",
            side, size, price, token_id[:12], resp,
        )
        return resp

    def buy(self, token_id: str, price: float, size: float) -> dict | None:
        return self.create_order(token_id, "BUY", price, size)

    def sell(self, token_id: str, price: float, size: float) -> dict | None:
        return self.create_order(token_id, "SELL", price, size)

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an active order."""
        if self.config.dry_run:
            logger.info("[DRY RUN] Cancel order %s", order_id)
            return {"dry_run": True}
        return self.client.cancel(order_id)

    def cancel_all_orders(self) -> dict:
        """Cancel all active orders."""
        if self.config.dry_run:
            logger.info("[DRY RUN] Cancel all orders")
            return {"dry_run": True}
        return self.client.cancel_all()

    def get_open_orders(self) -> list:
        """Get all open orders."""
        return self.client.get_orders()

    # ── Positions ─────────────────────────────────────────────────

    def get_positions(self) -> list:
        """Get current positions (balances)."""
        return self.client.get_balances()
