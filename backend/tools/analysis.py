from google.genai import types

ANALYSIS_TOOLS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="technical_signals",
        description=(
            "Compute technical indicators for a trading pair. Returns pre-computed "
            "RSI(14), MACD(12,26,9), Bollinger Bands(20), ATR(14), SMA(5/20/50), "
            "support/resistance, volume trend, and orderbook imbalance. "
            "Use this INSTEAD of manually computing indicators from raw candles."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="Trading pair, e.g. BTC/USD"),
                "interval": types.Schema(
                    type="INTEGER",
                    description="Candle interval in minutes. Default: 60 (1-hour candles)",
                ),
            },
            required=["pair"],
        ),
    ),
]
