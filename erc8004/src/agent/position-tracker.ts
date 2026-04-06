/**
 * Position tracker — maintains a local journal of open positions so the agent
 * can compute realized PnL when closing trades.
 *
 * Positions are stored in positions.json alongside checkpoints.jsonl.
 * When a SELL closes (or partially closes) a BUY, the tracker computes PnL
 * and returns it for inclusion in the on-chain attestation notes.
 */

import * as fs from "fs";
import * as path from "path";

const POSITIONS_FILE = path.join(process.cwd(), "positions.json");

export interface OpenPosition {
  pair: string;
  side: "BUY";
  entryPrice: number;
  volume: number;
  amountUsd: number;
  timestamp: number;
}

export interface PnLResult {
  pair: string;
  entryPrice: number;
  exitPrice: number;
  volume: number;
  pnlUsd: number;
  pnlPct: number;
}

function loadPositions(): OpenPosition[] {
  try {
    if (fs.existsSync(POSITIONS_FILE)) {
      return JSON.parse(fs.readFileSync(POSITIONS_FILE, "utf8"));
    }
  } catch {
    // corrupted file — start fresh
  }
  return [];
}

function savePositions(positions: OpenPosition[]): void {
  fs.writeFileSync(POSITIONS_FILE, JSON.stringify(positions, null, 2));
}

export function recordBuy(pair: string, price: number, volume: number, amountUsd: number): void {
  const positions = loadPositions();
  positions.push({
    pair,
    side: "BUY",
    entryPrice: price,
    volume,
    amountUsd,
    timestamp: Date.now(),
  });
  savePositions(positions);
  console.log(`[positions] Recorded BUY ${volume} ${pair} @ $${price.toFixed(2)}`);
}

export function recordSell(pair: string, exitPrice: number, volume: number): PnLResult | null {
  const positions = loadPositions();
  const idx = positions.findIndex(p => p.pair === pair);
  if (idx === -1) {
    console.log(`[positions] SELL ${pair} — no matching open position, recording as new short`);
    return null;
  }

  const pos = positions[idx];
  const closedVolume = Math.min(volume, pos.volume);
  const entryValue = closedVolume * pos.entryPrice;
  const exitValue = closedVolume * exitPrice;
  const pnlUsd = exitValue - entryValue;
  const pnlPct = ((exitPrice - pos.entryPrice) / pos.entryPrice) * 100;

  const result: PnLResult = {
    pair,
    entryPrice: pos.entryPrice,
    exitPrice,
    volume: closedVolume,
    pnlUsd,
    pnlPct,
  };

  if (closedVolume >= pos.volume) {
    positions.splice(idx, 1);
  } else {
    pos.volume -= closedVolume;
    pos.amountUsd -= closedVolume * pos.entryPrice;
  }
  savePositions(positions);

  const sign = pnlUsd >= 0 ? "+" : "";
  console.log(`[positions] Closed ${closedVolume} ${pair}: entry=$${pos.entryPrice.toFixed(2)} exit=$${exitPrice.toFixed(2)} PnL=${sign}$${pnlUsd.toFixed(2)} (${sign}${pnlPct.toFixed(2)}%)`);
  return result;
}

export function formatPnLNotes(pnl: PnLResult): string {
  const sign = pnl.pnlUsd >= 0 ? "+" : "";
  return `CLOSE ${pnl.pair}: entry=$${pnl.entryPrice.toFixed(2)} exit=$${pnl.exitPrice.toFixed(2)} pnl=${sign}$${pnl.pnlUsd.toFixed(2)} (${sign}${pnl.pnlPct.toFixed(2)}%)`;
}

export function getOpenPositions(): OpenPosition[] {
  return loadPositions();
}
