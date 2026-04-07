"""Local technical analysis — computed indicators fed to the LLM as structured signals.

The LLM receives pre-computed numbers (RSI, MACD, Bollinger, ATR, MAs) instead of
raw OHLC arrays. This keeps math accurate and lets the LLM focus on interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TechnicalSignals:
    pair: str
    price: float
    sma_5: float
    sma_20: float
    sma_50: float | None
    trend: str  # BULLISH / BEARISH / NEUTRAL
    rsi_14: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    bollinger_upper: float
    bollinger_middle: float
    bollinger_lower: float
    bollinger_pct_b: float
    atr_14: float
    volatility_pct: float
    support: float
    resistance: float
    volume_trend: str  # RISING / FALLING / FLAT
    orderbook_imbalance: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _coerce_candle(raw: Any) -> dict[str, float] | None:
    """Normalize candle input from dict or Kraken-style list/tuple."""
    if isinstance(raw, dict):
        try:
            return {
                "open": float(raw.get("open", 0.0)),
                "high": float(raw.get("high", 0.0)),
                "low": float(raw.get("low", 0.0)),
                "close": float(raw.get("close", 0.0)),
                "volume": float(raw.get("volume", 0.0)),
            }
        except (TypeError, ValueError):
            return None

    if isinstance(raw, (list, tuple)) and len(raw) >= 7:
        # Kraken OHLC array format:
        # [time, open, high, low, close, vwap, volume, count]
        try:
            return {
                "open": float(raw[1]),
                "high": float(raw[2]),
                "low": float(raw[3]),
                "close": float(raw[4]),
                "volume": float(raw[6]),
            }
        except (TypeError, ValueError, IndexError):
            return None

    return None


def _ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-(period):]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0001
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    if not ema_fast or not ema_slow:
        return 0.0, 0.0, 0.0
    min_len = min(len(ema_fast), len(ema_slow))
    macd_raw = [ema_fast[len(ema_fast) - min_len + i] - ema_slow[len(ema_slow) - min_len + i] for i in range(min_len)]
    if len(macd_raw) < signal:
        sig_val = macd_raw[-1] if macd_raw else 0.0
    else:
        sig_vals = _ema(macd_raw, signal)
        sig_val = sig_vals[-1] if sig_vals else macd_raw[-1]
    line = macd_raw[-1]
    return line, sig_val, line - sig_val


def _bollinger(closes: list[float], period: int = 20, num_std: float = 2.0) -> tuple[float, float, float, float]:
    """Returns (upper, middle, lower, %B)."""
    if len(closes) < period:
        p = closes[-1] if closes else 0
        return p, p, p, 0.5
    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((x - middle) ** 2 for x in window) / period
    std = variance ** 0.5
    upper = middle + num_std * std
    lower = middle - num_std * std
    band_width = upper - lower
    pct_b = (closes[-1] - lower) / band_width if band_width > 0 else 0.5
    return upper, middle, lower, pct_b


def _atr(candles: list[dict], period: int = 14) -> float:
    """Average True Range from OHLC candles."""
    if len(candles) < 2:
        return 0.0
    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        high = float(candles[i].get("high", 0))
        low = float(candles[i].get("low", 0))
        prev_close = float(candles[i - 1].get("close", 0))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    recent = true_ranges[-period:]
    return sum(recent) / len(recent) if recent else 0.0


def compute_signals(pair: str, candles: list[dict], ticker: dict | None = None, orderbook: dict | None = None) -> TechnicalSignals:
    """Compute all technical indicators from raw OHLC candle data.

    Args:
        pair: Trading pair (e.g. "XBTUSD").
        candles: List of OHLC dicts with keys: time, open, high, low, close, vwap, volume, count.
        ticker: Optional current ticker data for live price.
        orderbook: Optional orderbook dict with 'bids' and 'asks' arrays.
    """
    normalized_candles = [c for c in (_coerce_candle(raw) for raw in candles) if c is not None]
    closes = [c["close"] for c in normalized_candles]
    highs = [c["high"] for c in normalized_candles]
    lows = [c["low"] for c in normalized_candles]
    volumes = [c["volume"] for c in normalized_candles]

    price = closes[-1] if closes else 0.0
    if ticker:
        try:
            if isinstance(ticker, dict):
                # Handle direct price payload or pair-keyed payload.
                if "last" in ticker or "price" in ticker:
                    price = float(ticker.get("last", ticker.get("price", price)))
                else:
                    first = next((v for v in ticker.values() if isinstance(v, dict)), None)
                    if first:
                        # Kraken ticker uses "c": [last_trade_price, lot_volume]
                        if "c" in first and isinstance(first["c"], (list, tuple)) and first["c"]:
                            price = float(first["c"][0])
                        elif "last" in first:
                            price = float(first["last"])
                        elif "price" in first:
                            price = float(first["price"])
        except (TypeError, ValueError):
            pass

    if not normalized_candles:
        return TechnicalSignals(
            pair=pair,
            price=price,
            sma_5=price,
            sma_20=price,
            sma_50=None,
            trend="NEUTRAL",
            rsi_14=50.0,
            macd_line=0.0,
            macd_signal=0.0,
            macd_histogram=0.0,
            bollinger_upper=price,
            bollinger_middle=price,
            bollinger_lower=price,
            bollinger_pct_b=0.5,
            atr_14=0.0,
            volatility_pct=0.0,
            support=price,
            resistance=price,
            volume_trend="FLAT",
            orderbook_imbalance=None,
            extra={"warning": "insufficient_candles"},
        )

    sma_5 = _sma(closes, 5) or price
    sma_20 = _sma(closes, 20) or price
    sma_50 = _sma(closes, 50)

    if sma_5 > sma_20 * 1.003:
        trend = "BULLISH"
    elif sma_5 < sma_20 * 0.997:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    rsi = _rsi(closes, 14)
    macd_line, macd_sig, macd_hist = _macd(closes)
    bb_upper, bb_mid, bb_lower, bb_pct_b = _bollinger(closes)
    atr = _atr(normalized_candles, 14)

    recent_10 = normalized_candles[-10:] if len(normalized_candles) >= 10 else normalized_candles
    if recent_10:
        avg_range = (
            sum((c["high"] - c["low"]) / max(c["close"], 0.01) for c in recent_10)
            / len(recent_10)
            * 100
        )
    else:
        avg_range = 0.0

    support = min(lows[-24:]) if len(lows) >= 24 else min(lows) if lows else 0
    resistance = max(highs[-24:]) if len(highs) >= 24 else max(highs) if highs else 0

    if len(volumes) >= 10:
        vol_recent = sum(volumes[-5:]) / 5
        vol_prior = sum(volumes[-10:-5]) / 5
        if vol_recent > vol_prior * 1.1:
            vol_trend = "RISING"
        elif vol_recent < vol_prior * 0.9:
            vol_trend = "FALLING"
        else:
            vol_trend = "FLAT"
    else:
        vol_trend = "FLAT"

    ob_imbalance: float | None = None
    if orderbook:
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        bid_vol = sum(float(b[1]) if isinstance(b, (list, tuple)) else float(b.get("volume", 0)) for b in bids[:10])
        ask_vol = sum(float(a[1]) if isinstance(a, (list, tuple)) else float(a.get("volume", 0)) for a in asks[:10])
        total = bid_vol + ask_vol
        ob_imbalance = bid_vol / total if total > 0 else 0.5

    return TechnicalSignals(
        pair=pair,
        price=price,
        sma_5=sma_5,
        sma_20=sma_20,
        sma_50=sma_50,
        trend=trend,
        rsi_14=rsi,
        macd_line=macd_line,
        macd_signal=macd_sig,
        macd_histogram=macd_hist,
        bollinger_upper=bb_upper,
        bollinger_middle=bb_mid,
        bollinger_lower=bb_lower,
        bollinger_pct_b=bb_pct_b,
        atr_14=atr,
        volatility_pct=avg_range,
        support=support,
        resistance=resistance,
        volume_trend=vol_trend,
        orderbook_imbalance=ob_imbalance,
    )


def _rsi_label(rsi: float) -> str:
    if rsi >= 70:
        return "overbought"
    if rsi >= 60:
        return "bullish"
    if rsi <= 30:
        return "oversold"
    if rsi <= 40:
        return "bearish"
    return "neutral"


def _macd_label(hist: float, prev_hist: float = 0.0) -> str:
    if hist > 0 and hist > prev_hist:
        return "bullish, histogram expanding"
    if hist > 0:
        return "bullish, histogram contracting"
    if hist < 0 and hist < prev_hist:
        return "bearish, histogram expanding"
    if hist < 0:
        return "bearish, histogram contracting"
    return "flat"


def format_signals_for_llm(signals: TechnicalSignals) -> str:
    """Format computed signals as a structured text block for the LLM."""
    lines = [
        f"## Technical Analysis — {signals.pair} @ ${signals.price:,.2f}",
        "",
        f"Trend: {signals.trend} (SMA5=${signals.sma_5:,.2f} vs SMA20=${signals.sma_20:,.2f})",
        f"SMA50: {'$' + f'{signals.sma_50:,.2f}' if signals.sma_50 else 'insufficient data'}",
        f"RSI(14): {signals.rsi_14:.1f} ({_rsi_label(signals.rsi_14)})",
        f"MACD: line={signals.macd_line:.2f}, signal={signals.macd_signal:.2f}, histogram={signals.macd_histogram:.2f} ({_macd_label(signals.macd_histogram)})",
        f"Bollinger Bands: upper=${signals.bollinger_upper:,.2f}, mid=${signals.bollinger_middle:,.2f}, lower=${signals.bollinger_lower:,.2f}, %B={signals.bollinger_pct_b:.2f}",
        f"ATR(14): ${signals.atr_14:,.2f} (volatility={signals.volatility_pct:.2f}%)",
        f"Support: ${signals.support:,.2f} | Resistance: ${signals.resistance:,.2f}",
        f"Volume trend: {signals.volume_trend}",
    ]
    if signals.orderbook_imbalance is not None:
        pressure = "bullish" if signals.orderbook_imbalance > 0.55 else "bearish" if signals.orderbook_imbalance < 0.45 else "balanced"
        lines.append(f"Orderbook imbalance: {signals.orderbook_imbalance:.2f} ({pressure})")
    return "\n".join(lines)
