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
        description="Get OHLC (open, high, low, close) candle data for a pair.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="e.g. ETH/USD"),
                "interval": types.Schema(type="INTEGER", description="Candle interval in minutes (default 60)"),
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
