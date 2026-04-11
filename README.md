# AI-Trading-Agent

A multi-agent crypto trading system built for the Lablab.ai hackathon. It combines a **Python FastAPI backend** (market analyst, trader, and risk manager coordinated by an orchestrator), a **SvelteKit dashboard**, and an optional **ERC-8004 on-chain agent** under `erc8004/` that signs trade intents, talks to Kraken via the official CLI, and records EIP-712 checkpoints.

LLM calls use **Google Gemini** and/or **Mistral** (selectable in `config.yaml` / `LLM_PROVIDER`). Market data and orders go through the **[Kraken CLI](https://github.com/kraken-oss/kraken-cli)** with **paper trading by default**.

## Links
* Website: https://ai-trading-agent-production-8681.up.railway.app/llm
* Video presentation: https://www.youtube.com/watch?v=Mm65MyX3e9U
* Surge submission: https://early.surge.xyz/discovery/ai-mystery-inc

## Tech stack

- **Backend** — Python 3.12+ · FastAPI · Uvicorn · `google-genai` · `mistralai` · Redis (optional, for pipeline run history)
- **Frontend** — SvelteKit · TypeScript · Vite
- **On-chain agent** — Node.js 20+ · Hardhat · ethers v6 · Sepolia contracts (see `erc8004/`)

## Prerequisites

- Python 3.11+ (Dockerfile uses 3.12)
- Node.js 18+ for the frontend; **Node.js 20+** recommended for `erc8004/`
- [Kraken CLI](https://github.com/kraken-oss/kraken-cli) on your `PATH` (or set `KRAKEN_CLI_BINARY` in the environment / `kraken.cli_binary` in config)
- API keys for the LLM provider(s) you enable (see below)
- (Optional) Kraken API key and secret for authenticated CLI usage
- (Optional) Redis at `redis://localhost:6379/0` or set `REDIS_URL` for persisted pipeline history

## Environment variables

Create a `.env` file in the **project root** (same directory as `config.yaml`). There is no root `.env.example`; use this as a reference:

```bash
# LLMs (set at least one, matching agent.llm_provider in config.yaml)
GOOGLE_CLOUD_API_KEY=
MISTRAL_API_KEY=

# Kraken (CLI)
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
# Optional: path to the binary if not named `kraken` on PATH
KRAKEN_CLI_BINARY=kraken

# Optional
REDIS_URL=redis://localhost:6379/0
LLM_PROVIDER=mistral
```

`backend/config.py` loads `.env` and merges values with `config.yaml` (environment wins).

## Running the backend

From the **repository root**:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.api:app --reload --port 8000
```

The API is served at `http://localhost:8000`.

### CLI demos

Still from the repo root (with the venv activated):

```bash
python -m backend.main          # single-agent demo
python -m backend.main multi    # multi-agent orchestrator demo
```

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server defaults to Vite’s port (**5173**). The app expects the API at `http://localhost:8000` in development (see `frontend/src/lib/api.ts`).

## Running the ERC-8004 agent (`erc8004/`)

The on-chain loop delegates decisions to the Python pipeline (`POST /api/pipeline/run`) via `PythonApiStrategy`. Typical flow:

1. Start the FastAPI backend (above).
2. In another terminal:

```bash
cd erc8004
npm install
cp .env.example .env   # fill Sepolia RPC, keys, contract addresses, etc.
```

3. Optionally point the agent at a non-local API:

```bash
export PYTHON_API_URL=http://localhost:8000
```

4. Deploy / register if you are bringing your own contracts (see `erc8004/README.md`), then:

```bash
npm run run-agent
# optional second terminal:
npm run dashboard
```

More detail, contract addresses, and the step-by-step tutorial live in **`erc8004/README.md`**.

## Project structure

```
backend/
  api.py                 # FastAPI app (market, paper trading, pipeline, metrics)
  main.py                # CLI demos
  config.py              # Loads .env + config.yaml
  kraken_client.py       # Kraken CLI wrapper
  agents/                # Orchestrator, trader, market analyst, risk manager
  tools/                 # Agent tool definitions
  prompts/               # YAML prompts per agent
  store.py               # Optional Redis-backed pipeline / metrics store

frontend/
  src/routes/            # SvelteKit UI
  src/lib/api.ts         # HTTP client for the backend

erc8004/                 # Hardhat + TypeScript on-chain agent (see its README)
  contracts/
  src/agent/             # Loop, identity, python-api-strategy.ts
  scripts/

config.yaml              # Runtime settings (models, Kraken paper mode, risk_router, …)
requirements.txt
Dockerfile               # Production-style image: kraken CLI + uvicorn backend.api:app
```

## Docker

The root `Dockerfile` builds the Kraken CLI and runs `uvicorn backend.api:app` on port **8000** (or `PORT`).

## License

See [LICENSE](LICENSE).
