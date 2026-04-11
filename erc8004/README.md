# ERC-8004 on-chain agent (`erc8004/`)

This folder is the **on-chain trading loop** for the parent [AI-Trading-Agent](../README.md) repo: ERC-8004 identity, EIP-712 checkpoints, Risk Router validation, and **Kraken execution via the [Kraken CLI](https://github.com/kraken-oss/kraken-cli)** (paper mode supported through env — see `.env.example`).

The default strategy is **`PythonApiStrategy`**, which calls the root Python backend at `POST /api/pipeline/run` so each tick runs **Market Analyst → Trader → Risk Manager** before the template signs intents and interacts with Sepolia contracts.

The tutorial markdown under `tutorial/` and much of the Hardhat layout come from the [AI Trading Agent Template](https://github.com/Stephen-Kimoi/ai-trading-agent-template) (MIT), adapted for this monorepo and the Python pipeline.

---

## Architecture

```
PythonApiStrategy  →  POST /api/pipeline/run  (repo root backend)
       ↓
  TradingStrategy.analyze(market)  →  TradeDecision
       ↓
  RiskRouter.validateTrade()  (on-chain)
       ↓
  Kraken CLI  (orders + market data)
       ↓
  EIP-712 checkpoint  →  checkpoints.jsonl  (+ optional ValidationRegistry attestation)
```

---

## Prerequisites

- **Node.js 20+** (ethers v6 / toolchain)
- Sepolia ETH (e.g. [sepoliafaucet.com](https://sepoliafaucet.com))
- Infura, Alchemy, or another **Sepolia RPC URL**
- Kraken API key with permissions suitable for the CLI (see `.env.example` comments)

---

## Setup (inside this monorepo)

From the **repository root**:

```bash
cd erc8004
npm install
cp .env.example .env
# Edit .env: SEPOLIA_RPC_URL, PRIVATE_KEY / AGENT_WALLET_PRIVATE_KEY,
# KRAKEN_*, contract addresses, AGENT_ID, TRADING_PAIR, etc.
```

### Python backend URL

If the FastAPI app is not on `http://localhost:8000`, set:

```bash
export PYTHON_API_URL=https://your-api.example.com
```

This is read by `src/agent/python-api-strategy.ts` and `src/agent/index.ts`.

---

## Quickstart (own contracts)

### 1. Deploy contracts

```bash
cd erc8004
npx hardhat run scripts/deploy.ts --network sepolia
```

Copy the printed addresses into `.env` (`AGENT_REGISTRY_ADDRESS`, `HACKATHON_VAULT_ADDRESS`, `RISK_ROUTER_ADDRESS`, `REPUTATION_REGISTRY_ADDRESS`, `VALIDATION_REGISTRY_ADDRESS`).

### 2. Register the agent

```bash
npm run register
```

Set `AGENT_ID` in `.env` from the script output.

### 3. Run the agent (and optional dashboard)

Start the **root** Python API first (`uvicorn backend.api:app --reload --port 8000` from the repo root).

Then, in `erc8004/`:

```bash
# Terminal 1 — agent loop
npm run run-agent

# Terminal 2 — dashboard (default http://localhost:3000)
npm run dashboard
```

Other scripts: `npm run inspect-onchain`, `npm run claim`, `npm run deploy`, `npm test`.

---

## Swapping the strategy

The agent entrypoint is `src/agent/index.ts`. By default it instantiates **`PythonApiStrategy`** so decisions stay in sync with the Python multi-agent pipeline.

To use a purely local TypeScript strategy instead, change the import and the `strategy` construction at the bottom of `index.ts` (see `src/agent/strategy.ts` for the `TradingStrategy` interface and examples).

```typescript
interface TradingStrategy {
  analyze(data: MarketData): Promise<TradeDecision>;
}
```

---

## Tutorial

Step-by-step notes in `tutorial/`:

1. [What is ERC-8004 and why does it matter?](tutorial/01-erc8004-intro.md)
2. [Registering your agent on-chain](tutorial/02-register-agent.md)
3. [Connecting to Kraken](tutorial/03-kraken-connection.md)
4. [The Vault and Risk Router](tutorial/04-vault-riskrouter.md)
5. [Building the explanation layer](tutorial/05-explanation-layer.md)
6. [EIP-712 signed checkpoints](tutorial/06-eip712-checkpoints.md)
7. [Using this as a reusable template](tutorial/07-reusable-template.md)

---

## Project structure (high level)

```
contracts/           # Solidity: registry, vault, risk router, …
src/
  types/             # Shared TS types
  agent/             # index.ts loop, identity, python-api-strategy, …
  exchange/kraken.ts # Kraken CLI wrapper
  onchain/           # Vault, RiskRouter, registries
  explainability/    # Reasoning + EIP-712 checkpoints
scripts/
  deploy.ts
  register-agent.ts
  run-agent.ts
  dashboard.ts
  inspect-onchain.ts
  claim-allocation.ts
```

---

## Verify a checkpoint

```typescript
import { verifyCheckpoint } from "./src/explainability/checkpoint.js";

const valid = verifyCheckpoint(
  checkpoint,
  process.env.AGENT_REGISTRY_ADDRESS!,
  11155111,
  process.env.EXPECTED_SIGNER_ADDRESS!
);
console.log(valid); // true
```

---

## License

The **overall repository** is licensed under the MIT License — see the root [`LICENSE`](../LICENSE). Third-party tutorial/template portions retain their original terms where applicable.
