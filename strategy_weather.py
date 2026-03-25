"""Weather-based trading strategy using NOAA public forecast data.

Uses the free NOAA Weather API (https://api.weather.gov) to get temperature
forecasts for major US cities and compares them against Polymarket weather
market prices to find mispriced opportunities.

NOAA City → Endpoint Mapping:
  Each city maps to a weather station (gridpoint). To find a city's endpoint:
  1. GET https://api.weather.gov/points/{lat},{lon}  (e.g. 41.8781,-87.6298 for Chicago)
  2. Response contains "forecast" URL like:
     https://api.weather.gov/gridpoints/{office}/{gridX},{gridY}/forecast
  The CITY_GRID_POINTS dict below stores pre-resolved office/gridX/gridY values.
"""

import re
import time
import requests

from strategies import Strategy
from client import PolymarketClient
from risk import RiskManager
from logger import setup_logger

logger = setup_logger("weather_strategy")

# Pre-resolved NOAA gridpoints for supported cities.
# Format: "City Name" -> (office, gridX, gridY)
# To add a new city:
#   curl https://api.weather.gov/points/{lat},{lon}
#   Extract: properties.gridId, properties.gridX, properties.gridY
CITY_GRID_POINTS = {
    "Chicago": ("LOT", 76, 73),
    "New York": ("OKX", 33, 37),
    "Los Angeles": ("LOX", 154, 44),
    "Miami": ("MFL", 110, 65),
    "Houston": ("HGX", 65, 97),
    "Phoenix": ("PSR", 159, 57),
    "Denver": ("BOU", 62, 60),
    "Seattle": ("SEW", 124, 67),
    "Atlanta": ("FFC", 50, 86),
    "Dallas": ("FWD", 84, 108),
}

# Regex patterns to identify weather/temperature markets in Polymarket
WEATHER_PATTERNS = [
    re.compile(r"temperature.*?(above|below|over|under|exceed|reach)\s+(\d+)", re.IGNORECASE),
    re.compile(r"(above|below|over|under|exceed|reach)\s+(\d+)\s*°?\s*[fF]", re.IGNORECASE),
    re.compile(r"(\d+)\s*°?\s*[fF].*?(or\s+)?(higher|lower|warmer|colder|above|below)", re.IGNORECASE),
    re.compile(r"high\s+temp.*?(\d+)", re.IGNORECASE),
]

# Which cities to look for in market question text
CITY_ALIASES = {
    "Chicago": ["Chicago", "CHI"],
    "New York": ["New York", "NYC", "Manhattan"],
    "Los Angeles": ["Los Angeles", "LA", "L.A."],
    "Miami": ["Miami", "MIA"],
    "Houston": ["Houston", "HOU"],
    "Phoenix": ["Phoenix", "PHX"],
    "Denver": ["Denver", "DEN"],
    "Seattle": ["Seattle", "SEA"],
    "Atlanta": ["Atlanta", "ATL"],
    "Dallas": ["Dallas", "DFW"],
}

NOAA_HEADERS = {
    "User-Agent": "(PolymarketWeatherBot, contact@example.com)",
    "Accept": "application/geo+json",
}


class WeatherStrategy(Strategy):
    """Buy weather markets when NOAA forecasts disagree with market price.

    Only generates BUY signals when:
    - Market is identified as a temperature market for a supported city
    - NOAA forecast confidence is high
    - Edge (NOAA probability - market price) exceeds min_edge threshold
    - Market spread is tight enough for liquid execution
    """

    def __init__(self, client: PolymarketClient, risk: RiskManager,
                 min_edge: float = 0.20, cities: list[str] | None = None,
                 max_spread: float = 0.08, max_positions: int = 4):
        super().__init__(client, risk)
        self.min_edge = min_edge
        self.cities = cities or ["Chicago", "New York", "Los Angeles"]
        self.max_spread = max_spread
        self.max_positions = max_positions
        # Cache NOAA forecasts to avoid hammering the API (city -> (timestamp, data))
        self._forecast_cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl = 600  # 10 minutes

    def evaluate(self, token_id: str, market_info: dict) -> list[dict]:
        signals = []
        question = market_info.get("question", "")

        # Skip if already in too many positions
        if len(self.risk.positions) >= self.max_positions and token_id not in self.risk.positions:
            return signals

        # Step 1: Is this a weather/temperature market?
        city, threshold_temp, direction = self._parse_weather_market(question)
        if city is None:
            return signals

        # Step 2: Get current market price
        try:
            price_data = self.client.get_price(token_id)
            mid = (price_data["bid"] + price_data["ask"]) / 2
        except Exception as e:
            logger.debug("Failed to get price for %s: %s", token_id[:12], e)
            return signals

        # Skip illiquid markets
        if price_data["spread"] > self.max_spread:
            return signals

        # Step 3: Get NOAA forecast
        forecast = self._get_forecast(city)
        if forecast is None:
            return signals

        # Step 4: Calculate NOAA-implied probability
        noaa_prob = self._calculate_noaa_probability(forecast, threshold_temp, direction)
        if noaa_prob is None:
            return signals

        # Step 5: Compare with market price and generate signal if edge exists
        edge = noaa_prob - mid
        logger.info(
            "Weather: %s | %s %d°F | NOAA=%.2f vs Market=%.2f | Edge=%.2f",
            city, direction, threshold_temp, noaa_prob, mid, edge,
        )

        if edge >= self.min_edge:
            signals.append({
                "action": "BUY",
                "price": price_data["ask"],
                "size": self.client.config.order_size,
                "reason": (
                    f"Weather: {city} {direction} {threshold_temp}°F | "
                    f"NOAA {noaa_prob:.0%} vs Mkt {mid:.0%} | Edge {edge:.0%}"
                ),
            })

        return signals

    def _parse_weather_market(self, question: str) -> tuple:
        """Extract city, temperature threshold, and direction from market question.

        Returns (city, threshold_temp, direction) or (None, None, None).
        direction is "above" or "below".
        """
        # Find which city this market is about
        city = None
        for city_name in self.cities:
            aliases = CITY_ALIASES.get(city_name, [city_name])
            for alias in aliases:
                if alias.lower() in question.lower():
                    city = city_name
                    break
            if city:
                break

        if city is None:
            return None, None, None

        # Find temperature threshold and direction
        for pattern in WEATHER_PATTERNS:
            match = pattern.search(question)
            if match:
                groups = match.groups()
                # Extract the numeric temperature value
                temp = None
                direction_word = None
                for g in groups:
                    if g and g.isdigit():
                        temp = int(g)
                    elif g and g.lower() in (
                        "above", "over", "exceed", "reach", "higher", "warmer",
                        "below", "under", "lower", "colder",
                    ):
                        direction_word = g.lower()

                if temp is not None and direction_word is not None:
                    direction = "above" if direction_word in (
                        "above", "over", "exceed", "reach", "higher", "warmer"
                    ) else "below"
                    return city, temp, direction

        return None, None, None

    def _get_forecast(self, city: str) -> dict | None:
        """Fetch NOAA forecast for a city, using cache when available."""
        now = time.time()
        if city in self._forecast_cache:
            ts, data = self._forecast_cache[city]
            if now - ts < self._cache_ttl:
                return data

        grid = CITY_GRID_POINTS.get(city)
        if grid is None:
            return None

        office, grid_x, grid_y = grid
        url = f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}/forecast"

        try:
            resp = requests.get(url, headers=NOAA_HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._forecast_cache[city] = (now, data)
            logger.info("NOAA forecast fetched for %s", city)
            return data
        except Exception as e:
            logger.warning("NOAA API error for %s: %s", city, e)
            return None

    def _calculate_noaa_probability(
        self, forecast: dict, threshold: int, direction: str
    ) -> float | None:
        """Estimate probability that temperature will be above/below threshold.

        Uses the next 24-48h forecast periods from NOAA.
        NOAA forecasts have ~94% accuracy at 24h for temperature.

        Returns a probability between 0.0 and 1.0, or None if uncertain.
        """
        try:
            periods = forecast["properties"]["periods"]
        except (KeyError, TypeError):
            return None

        if not periods:
            return None

        # Look at daytime periods in the next 48 hours (up to 4 periods)
        relevant_temps = []
        for period in periods[:4]:
            temp = period.get("temperature")
            unit = period.get("temperatureUnit", "F")
            if temp is None:
                continue
            # Convert Celsius to Fahrenheit if needed
            if unit == "C":
                temp = temp * 9 / 5 + 32
            # Only use daytime highs for "above" and nighttime lows for "below"
            is_daytime = period.get("isDaytime", True)
            if direction == "above" and is_daytime:
                relevant_temps.append(temp)
            elif direction == "below" and not is_daytime:
                relevant_temps.append(temp)
            elif direction == "above" and not is_daytime:
                # Night temps still useful as lower bound
                relevant_temps.append(temp)
            elif direction == "below" and is_daytime:
                relevant_temps.append(temp)

        if not relevant_temps:
            return None

        # Use the most relevant temperature (next daytime high or nighttime low)
        if direction == "above":
            forecast_temp = max(relevant_temps)
            diff = forecast_temp - threshold
        else:
            forecast_temp = min(relevant_temps)
            diff = threshold - forecast_temp

        # Convert temperature difference to probability estimate.
        # NOAA has ~2-3°F standard error at 24h.
        # We use a conservative estimate with stddev=3°F.
        noaa_stddev = 3.0

        if diff > 3 * noaa_stddev:
            prob = 0.98  # Very confident
        elif diff > 2 * noaa_stddev:
            prob = 0.95
        elif diff > noaa_stddev:
            prob = 0.85
        elif diff > 0:
            prob = 0.65
        elif diff > -noaa_stddev:
            prob = 0.35
        elif diff > -2 * noaa_stddev:
            prob = 0.10
        else:
            prob = 0.02  # Very unlikely

        logger.debug(
            "NOAA calc: forecast=%d°F, threshold=%d°F, diff=%.1f, prob=%.2f",
            forecast_temp, threshold, diff, prob,
        )

        # If probability is in the uncertain zone (0.35-0.65), return None
        # to avoid trading on low-confidence signals
        if 0.30 < prob < 0.70:
            logger.info(
                "NOAA: %s %d°F - forecast too close to threshold (prob=%.2f), skipping",
                direction, threshold, prob,
            )
            return None

        return prob
