from google.genai import types

LIVE_TRADE_TOOLS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="buy",
        description="Place a REAL buy order on Kraken (requires API keys and funds).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="e.g. BTC/USD"),
                "volume": types.Schema(type="STRING", description="Order size"),
            },
            required=["pair", "volume"],
        ),
    ),
    types.FunctionDeclaration(
        name="sell",
        description="Place a REAL sell order on Kraken (requires API keys and funds).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pair": types.Schema(type="STRING", description="e.g. BTC/USD"),
                "volume": types.Schema(type="STRING", description="Order size"),
            },
            required=["pair", "volume"],
        ),
    ),
    types.FunctionDeclaration(
        name="balance",
        description="Show current real account balances on Kraken.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="open_orders",
        description="Show open live orders on Kraken.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
]
