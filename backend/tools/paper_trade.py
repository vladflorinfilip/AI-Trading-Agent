from google.genai import types

PAPER_TRADE_TOOLS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="paper_buy",
        description="Place a paper (simulated) buy order.",
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
        name="paper_sell",
        description="Place a paper (simulated) sell order.",
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
        name="paper_balance",
        description="Show current paper-trading balances.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="paper_positions",
        description="Show open paper-trading positions.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
]
