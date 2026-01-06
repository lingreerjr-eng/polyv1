"""
Utility functions and helpers
"""

import time
from datetime import datetime


def format_timestamp(timestamp: float) -> str:
    """Format unix timestamp as readable string"""
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def format_duration(seconds: float) -> str:
    """Format duration in seconds as readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def calculate_percentage_change(old_price: float, new_price: float) -> float:
    """Calculate percentage change between two prices"""
    return (new_price - old_price) / old_price


def round_to_cents(price: float) -> float:
    """Round price to nearest cent"""
    return round(price * 100) / 100


def is_market_hours() -> bool:
    """
    Check if it's good trading hours
    Crypto markets are 24/7, but Polymarket volume is higher during US hours
    """
    hour = datetime.now().hour
    # 9 AM to 9 PM EST (14:00 to 02:00 UTC)
    return 9 <= hour <= 21


def get_unix_timestamp_15min_window(timestamp: float = None) -> int:
    """
    Get the unix timestamp for the current 15-minute window

    Markets are typically created on the quarter hour:
    8:00, 8:15, 8:30, 8:45, etc.
    """
    if timestamp is None:
        timestamp = time.time()

    # Round down to nearest 15 minutes
    minutes = int(timestamp / 60)
    rounded_minutes = (minutes // 15) * 15

    return rounded_minutes * 60


def format_money(amount: float) -> str:
    """Format dollar amount with proper sign and decimals"""
    sign = "+" if amount >= 0 else ""
    return f"{sign}${amount:.2f}"


def calculate_kelly_criterion(win_prob: float, odds: float) -> float:
    """
    Calculate optimal position size using Kelly Criterion

    Kelly % = (win_prob × (1 - odds) - (1 - win_prob) × odds) / (1 - odds)

    Returns: Fraction of bankroll to bet (0.0 to 1.0)
    """
    if odds >= 1.0 or odds <= 0.0:
        return 0.0

    numerator = (win_prob * (1 - odds)) - ((1 - win_prob) * odds)
    denominator = 1 - odds

    kelly_fraction = numerator / denominator if denominator != 0 else 0.0

    # Cap at 25% (fractional Kelly for safety)
    return max(0.0, min(0.25, kelly_fraction))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is 0"""
    return numerator / denominator if denominator != 0 else default


def moving_average(values: list, window: int) -> float:
    """Calculate simple moving average"""
    if len(values) < window:
        window = len(values)

    if window == 0:
        return 0.0

    return sum(values[-window:]) / window
