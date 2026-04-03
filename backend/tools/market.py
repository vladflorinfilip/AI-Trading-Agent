from google.genai import types

MARKET_TOOLS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="ticker",
        description="Get current ticker (price, volume, spread) for a trading pair.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="e.g. BTC/USD"),
            },
            required=["pair"],
        ),
    ),
    types.FunctionDeclaration(
        name="ohlc",
        description=(
            "Get OHLC candlestick data for a trading pair. "
            "Returns an array of candles, each with fields: "
            "time (unix timestamp), open, high, low, close, vwap (volume-weighted avg price), "
            "volume, and count (number of trades). "
            "Use interval=60 for 1-hour candles (recommended for swing trading). "
            "Typically returns the last 720 candles. "
            "Use the closing prices to compute moving averages, identify trend direction, "
            "and find support (lowest low) and resistance (highest high) levels."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="Trading pair, e.g. BTC/USD or ETH/USD"),
                "interval": types.Schema(
                    type="INTEGER",
                    description="Candle interval in minutes. Common values: 1, 5, 15, 30, 60, 240, 1440. Default: 60",
                ),
            },
            required=["pair"],
        ),
    ),
    types.FunctionDeclaration(
        name="orderbook",
        description="Get order book (bids & asks) for a pair.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="e.g. BTC/USD"),
                "count": types.Schema(type="INTEGER", description="Depth (default 10)"),
            },
            required=["pair"],
        ),
    ),
]
