/**
 * Strategy that delegates decision-making to the Python multi-agent pipeline.
 *
 * Calls POST /api/pipeline/run on the FastAPI backend, which runs:
 *   MarketAnalyst → Trader → RiskManager
 *
 * The pipeline returns a structured result with stages and a decision
 * (BUY / SELL / HOLD). This strategy maps that response back into a
 * TradeDecision for the template's agent loop to process.
 */

import { MarketData, TradeDecision, TradingStrategy } from "../types/index";

const PYTHON_API_URL = process.env.PYTHON_API_URL || "http://localhost:8000";

export class PythonApiStrategy implements TradingStrategy {
  private readonly apiUrl: string;
  private readonly tradeAmountUsd: number;

  constructor(tradeAmountUsd = 100) {
    this.apiUrl = PYTHON_API_URL;
    this.tradeAmountUsd = tradeAmountUsd;
  }

  async analyze(data: MarketData): Promise<TradeDecision> {
    const query =
      `Live market data for ${data.pair}: ` +
      `price=$${data.price}, bid=$${data.bid}, ask=$${data.ask}, ` +
      `high=$${data.high}, low=$${data.low}, vwap=$${data.vwap}, ` +
      `volume=${data.volume}. ` +
      `Analyse and decide whether to BUY, SELL, or HOLD.`;

    try {
      const res = await fetch(`${this.apiUrl}/api/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) {
        const detail = await res.text();
        console.warn(`[python-api] Pipeline returned ${res.status}: ${detail}`);
        return this.fallbackHold(data, `Pipeline error: ${res.status}`);
      }

      const json = (await res.json()) as PipelineResponse;

      const action = this.parseAction(json.decision);
      const traderStage = json.stages?.[1];
      const reasoning =
        traderStage?.response ?? json.decision ?? "No reasoning returned";

      return {
        action,
        asset: data.pair.replace("USD", ""),
        pair: data.pair,
        amount: action === "HOLD" ? 0 : this.tradeAmountUsd,
        confidence: this.inferConfidence(action, reasoning),
        reasoning,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`[python-api] Failed to reach Python backend: ${msg}`);
      return this.fallbackHold(data, `API unreachable: ${msg}`);
    }
  }

  private parseAction(raw: string | undefined): TradeDecision["action"] {
    if (!raw) return "HOLD";
    const upper = raw.toUpperCase();
    if (upper === "BUY") return "BUY";
    if (upper === "SELL") return "SELL";
    return "HOLD";
  }

  private inferConfidence(
    action: TradeDecision["action"],
    reasoning: string
  ): number {
    const hasStrong = /strong|clear|significant|confident|breakout|momentum/i.test(reasoning);
    if (action === "HOLD") return hasStrong ? 0.80 : 0.70;
    return hasStrong ? 0.85 : 0.75;
  }

  private fallbackHold(data: MarketData, reason: string): TradeDecision {
    return {
      action: "HOLD",
      asset: data.pair.replace("USD", ""),
      pair: data.pair,
      amount: 0,
      confidence: 0.5,
      reasoning: `[FALLBACK] ${reason}. Holding position.`,
    };
  }
}

interface PipelineResponse {
  decision: string;
  stages: Array<{
    agent: string;
    response: string;
    duration_ms: number;
  }>;
  total_duration_ms: number;
  id?: string;
  timestamp?: string;
}
