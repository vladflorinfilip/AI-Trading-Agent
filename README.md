# AI-Trading-Agent

A multi-agent crypto trading system built for the Lablab.ai hackathon. It uses **Google Gemini** as the LLM backbone and the **Kraken CLI** for market data and order execution. Specialised agents (market analyst, risk manager, trader) are coordinated by an orchestrator to analyse markets and execute paper trades.

## Tech Stack

- **Backend** — Python 3 · FastAPI · Uvicorn · Google GenAI SDK
- **Frontend** — SvelteKit · TypeScript · Vite
- **LLM** — Gemini 3.1 Flash Lite (configurable in `config.yaml`)
- **Exchange** — Kraken (via CLI, paper-trading by default)

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Kraken CLI](https://github.com/kratercoin/kraken-cli) binary built and accessible
- A Google Cloud / Gemini API key
- (Optional) Kraken API key and secret for live data

## Environment Variables

Copy `.env.example` or create a `.env` file in the project root:

```
GOOGLE_CLOUD_API_KEY=<your-gemini-api-key>
KRAKEN_API_KEY=<your-kraken-api-key>
KRAKEN_API_SECRET=<your-kraken-api-secret>
```

## Running the Backend

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the API server (port 8000)
uvicorn ai_trading_agent.api:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

### CLI Demo

You can also run the agents directly from the terminal:

```bash
python -m ai_trading_agent.main          # single-agent demo
python -m ai_trading_agent.main multi    # multi-agent orchestrator demo
```

## Running the Frontend

```bash
# 1. Install dependencies
cd frontend
npm install

# 2. Start the dev server (port 5173)
npm run dev
```

Open `http://localhost:5173` in your browser. The frontend expects the backend to be running on port 8000.

## Project Structure

```
ai_trading_agent/
├── api.py              # FastAPI REST API
├── main.py             # CLI entry point
├── config.py           # Loads .env + config.yaml
├── kraken_client.py    # Kraken CLI wrapper
├── agents/             # Orchestrator, trader, market analyst, risk manager
├── tools/              # Market data & paper-trade tool definitions
└── prompts/            # YAML prompt templates per agent

frontend/
├── src/
│   ├── routes/         # SvelteKit pages
│   └── lib/api.ts      # Backend HTTP client
├── package.json
└── svelte.config.js

config.yaml             # Runtime configuration (model, agent limits, etc.)
requirements.txt        # Python dependencies
.env                    # API keys (not committed)
```

## License

See [LICENSE](LICENSE).
