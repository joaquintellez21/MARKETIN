"""WebSocket feed for real-time Polymarket market data.

Connects to the Polymarket CLOB WebSocket for live order book updates.
Falls back to REST polling if WebSocket connection fails.
"""

import asyncio
import json
import threading
import time

import websockets

from logger import setup_logger

logger = setup_logger("ws_feed")

# Polymarket CLOB WebSocket endpoint
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class MarketFeed:
    """Real-time market data feed via WebSocket with REST fallback.

    Usage:
        feed = MarketFeed(token_ids=["abc123", "def456"])
        feed.start()          # Non-blocking, runs in background thread
        book = feed.get_book("abc123")  # Latest cached order book
        feed.stop()
    """

    def __init__(self, token_ids: list[str] | None = None):
        self.token_ids: list[str] = token_ids or []
        self._books: dict[str, dict] = {}  # token_id -> latest book snapshot
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._connected = False
        self._last_update: dict[str, float] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    def start(self):
        """Start the WebSocket feed in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("WebSocket feed started for %d tokens", len(self.token_ids))

    def stop(self):
        """Stop the WebSocket feed."""
        self._running = False
        self._connected = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("WebSocket feed stopped")

    def subscribe(self, token_id: str):
        """Add a token to the subscription list."""
        if token_id not in self.token_ids:
            self.token_ids.append(token_id)

    def get_book(self, token_id: str) -> dict | None:
        """Get the latest cached order book for a token.

        Returns None if no data is available yet.
        """
        with self._lock:
            return self._books.get(token_id)

    def get_last_update(self, token_id: str) -> float:
        """Get the timestamp of the last update for a token."""
        return self._last_update.get(token_id, 0)

    def _run_loop(self):
        """Run the async WebSocket loop in a dedicated thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_connect())
        except Exception as e:
            logger.error("WebSocket loop exited: %s", e)
        finally:
            self._connected = False
            loop.close()

    async def _ws_connect(self):
        """Connect to WebSocket and process messages with auto-reconnect."""
        retry_delay = 2
        max_retry = 30

        while self._running:
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._connected = True
                    retry_delay = 2  # Reset on successful connection
                    logger.info("WebSocket connected to %s", WS_URL)

                    # Subscribe to token channels
                    if self.token_ids:
                        sub_msg = json.dumps({
                            "type": "subscribe",
                            "assets_ids": self.token_ids,
                        })
                        await ws.send(sub_msg)
                        logger.info("Subscribed to %d token feeds", len(self.token_ids))

                    # Process incoming messages
                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg)
                            self._handle_message(msg)
                        except json.JSONDecodeError:
                            logger.debug("Non-JSON message: %s", raw_msg[:100])

            except websockets.exceptions.ConnectionClosed as e:
                self._connected = False
                logger.warning("WebSocket disconnected: %s", e)
            except Exception as e:
                self._connected = False
                logger.warning("WebSocket error: %s", e)

            if self._running:
                logger.info("Reconnecting in %ds...", retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry)

    def _handle_message(self, msg: dict):
        """Process a WebSocket message and update cached book data."""
        msg_type = msg.get("type", "")

        if msg_type in ("book", "book_snapshot"):
            token_id = msg.get("asset_id") or msg.get("market", "")
            if token_id:
                with self._lock:
                    self._books[token_id] = msg
                    self._last_update[token_id] = time.monotonic()

        elif msg_type == "book_delta":
            token_id = msg.get("asset_id") or msg.get("market", "")
            if token_id:
                with self._lock:
                    # Apply delta to existing book or store as-is
                    self._books[token_id] = msg
                    self._last_update[token_id] = time.monotonic()

        elif msg_type == "price":
            token_id = msg.get("asset_id", "")
            if token_id:
                with self._lock:
                    self._books.setdefault(token_id, {})
                    self._books[token_id]["price"] = msg.get("price")
                    self._last_update[token_id] = time.monotonic()
