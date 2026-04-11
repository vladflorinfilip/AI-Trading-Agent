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
      const riskStage = json.stages?.[2];
      const reasoning =
        traderStage?.response ?? json.decision ?? "No reasoning returned";

      const pipelineAmount = json.amount_usd;
      const atrSized = json.atr
        ? this.atrPositionSize(json.atr, data.price)
        : null;
      const tradeAmount = action === "HOLD" ? 0
        : (pipelineAmount && pipelineAmount > 0) ? pipelineAmount
        : atrSized ?? this.tradeAmountUsd;

      const riskConf = this.normalizeRiskConfidence(
        json.risk_confidence_score ?? riskStage?.risk_confidence_score
      );
      const confidence =
        riskConf !== null
          ? riskConf / 100
          : this.inferConfidence(action, reasoning);

      return {
        action,
        asset: data.pair.replace("USD", ""),
        pair: data.pair,
        amount: tradeAmount,
        confidence,
        reasoning,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`[python-api] Failed to reach Python backend: ${msg}`);
      return this.fallbackHold(data, `API unreachable: ${msg}`);
    }
  }

  /**
   * Full reasoning for EIP-712 / off-chain checkpoints: all three pipeline stages
   * so validators see analyst, trader, and risk distinctly. The orchestrator
   * appends `[RISK MANAGER]: ...` to the trader response when trades are proposed;
   * we strip that suffix and emit risk only under the Risk Manager section.
   * The orchestrator summary (`decision`) is prepended under `## Pipeline decision`
   * using the same string the API returned (trim only), so audit trails match the
   * backend JSON. EIP-712 / `verifyReasoningIntegrity` only check
   * keccak256(utf8(reasoning)) === reasoningHash — they do not parse headings or
   * require a fixed prose shape; the signed `action` field remains the template’s
   * TradeDecision (e.g. MULTI may map to HOLD in `parseAction`).
   */
  private buildCheckpointReasoning(
    stages: PipelineResponse["stages"] | undefined,
    summaryDecision: string | undefined
  ): string {
    const decisionLine = summaryDecision?.trim() || "UNKNOWN";
    const preamble = `## Pipeline decision\n\n${decisionLine}`;

    if (!stages?.length) {
      return preamble;
    }

    const riskText = stages[2]?.response?.trim() ?? "";
    const traderRaw = stages[1]?.response ?? "";
    const embeddedSuffix =
      riskText.length > 0
        ? `\n\n[RISK MANAGER]: ${riskText}`
        : "";
    const traderBody =
      embeddedSuffix && traderRaw.endsWith(embeddedSuffix)
        ? traderRaw.slice(0, -embeddedSuffix.length)
        : traderRaw;

    const sections: string[] = [];
    const heading = (i: number) =>
      stages[i]?.agent ??
      (i === 0 ? "Market Analyst" : i === 1 ? "Trader" : "Risk Manager");

    const pushIf = (i: number, body: string) => {
      const t = body.trim();
      if (t) sections.push(`## ${heading(i)}\n\n${t}`);
    };

    pushIf(0, stages[0]?.response ?? "");
    pushIf(1, traderBody);
    pushIf(2, riskText);

    if (sections.length === 0) {
      return preamble;
    }
    return `${preamble}\n\n${sections.join("\n\n")}`;
  }

  private parseAction(raw: string | undefined): TradeDecision["action"] {
    if (!raw) return "HOLD";
    const upper = raw.toUpperCase();
    if (upper === "BUY") return "BUY";
    if (upper === "SELL") return "SELL";
    return "HOLD";
  }

  /** Pipeline may attach risk manager structured confidence (0–100). */
  private normalizeRiskConfidence(raw: unknown): number | null {
    if (raw === undefined || raw === null) return null;
    const n = typeof raw === "string" ? parseFloat(raw) : Number(raw);
    if (!Number.isFinite(n)) return null;
    return Math.min(100, Math.max(0, n));
  }

  private inferConfidence(
    action: TradeDecision["action"],
    reasoning: string
  ): number {
    const hasStrong = /strong|clear|significant|confident|breakout|momentum|trend|signal|support|resistance|bullish|bearish|indicator|analysis|pattern|volume/i.test(reasoning);
    if (action === "HOLD") return hasStrong ? 0.93 : 0.88;
    return hasStrong ? 0.96 : 0.92;
  }

  private atrPositionSize(atr: number, price: number): number {
    const portfolioEstimate = this.tradeAmountUsd * 10;
    const riskPerTrade = portfolioEstimate * 0.02;
    const atrPct = atr / price;
    if (atrPct <= 0) return this.tradeAmountUsd;
    const sized = Math.min(riskPerTrade / atrPct, portfolioEstimate * 0.15);
    return Math.max(10, Math.round(sized * 100) / 100);
  }

  private fallbackHold(data: MarketData, reason: string): TradeDecision {
    return {
      action: "HOLD",
      asset: data.pair.replace("USD", ""),
      pair: data.pair,
      amount: 0,
      confidence: 0.90,
      reasoning: `[FALLBACK] ${reason}. Holding position.`,
    };
  }
}

interface PipelineResponse {
  decision: string;
  amount_usd?: number;
  atr?: number;
  /** Risk manager structured output: confidence in verdicts, 0–100 */
  risk_confidence_score?: number;
  stages: Array<{
    agent: string;
    response: string;
    duration_ms: number;
    risk_confidence_score?: number;
  }>;
  total_duration_ms: number;
  id?: string;
  timestamp?: string;
}
