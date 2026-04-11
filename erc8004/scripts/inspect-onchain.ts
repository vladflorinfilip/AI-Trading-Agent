/**
 * Read-only snapshot of on-chain signals for your agentId.
 * Use this to verify the agent is touching contracts vs what the leaderboard shows.
 *
 *   cd erc8004 && npx ts-node scripts/inspect-onchain.ts
 *
 * Requires: SEPOLIA_RPC_URL, AGENT_ID, VALIDATION_REGISTRY_ADDRESS,
 *           RISK_ROUTER_ADDRESS, optional REPUTATION_REGISTRY_ADDRESS
 */

import * as dotenv from "dotenv";
dotenv.config();

import { ethers } from "ethers";
import { ValidationRegistryClient } from "../src/onchain/validationRegistry";
import { ReputationRegistryClient } from "../src/onchain/reputationRegistry";
import { RiskRouterClient } from "../src/onchain/riskRouter";

function req(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing env ${name}`);
  return v;
}

function fmtBlockTime(ts: number): string {
  if (ts <= 0) return "(invalid)";
  const d = new Date(ts * 1000);
  return `${d.toISOString()} (unix ${ts})`;
}

async function main() {
  const rpc = req("SEPOLIA_RPC_URL");
  const agentId = BigInt(req("AGENT_ID"));
  const validationAddr = req("VALIDATION_REGISTRY_ADDRESS");
  const routerAddr = req("RISK_ROUTER_ADDRESS");
  const reputationAddr = process.env.REPUTATION_REGISTRY_ADDRESS || "";

  const provider = new ethers.JsonRpcProvider(rpc);
  const validation = new ValidationRegistryClient(validationAddr, provider);
  const riskRouter = new RiskRouterClient(routerAddr, provider, 11155111);

  const [attCount, valAvg, tradeRec] = await Promise.all([
    validation.getAttestationCount(agentId),
    validation.getAverageScore(agentId),
    riskRouter.getTradeRecord(agentId),
  ]);

  console.log("\n── Agent ──");
  console.log(`agentId:              ${agentId}`);
  console.log(`RiskRouter trades/hr: ${tradeRec.count} (window start ${tradeRec.windowStart})`);

  console.log("\n── ValidationRegistry ──");
  console.log(`attestationCount:     ${attCount}`);
  console.log(`getAverageScore (raw contract): ${valAvg}`);
  console.log(
    "(Leaderboard may use a different formula or only certain validators — this is the on-chain mean of every attestation row.)"
  );

  const atts = await validation.getAttestations(agentId);
  if (atts.length > 0) {
    const last = atts[atts.length - 1];
    const newestTs = Math.max(...atts.map((a) => a.timestamp));
    console.log(`\nlast attestation (append order):  ${fmtBlockTime(last.timestamp)}`);
    console.log(`newest attestation timestamp:       ${fmtBlockTime(newestTs)}`);
  }

  const tail = atts.slice(-8);
  if (tail.length === 0) {
    console.log("recent attestations:  (none)");
  } else {
    console.log(`\nlast ${tail.length} attestation(s) (time → validator → score):`);
    for (const a of tail) {
      console.log(
        `  ${fmtBlockTime(a.timestamp)}  ${a.validator.slice(0, 10)}…  score=${a.score}  hash=${a.checkpointHash.slice(0, 14)}…`
      );
    }
    const byValidator = new Map<string, { count: number; sum: number }>();
    for (const a of atts) {
      const k = a.validator.toLowerCase();
      const cur = byValidator.get(k) || { count: 0, sum: 0 };
      cur.count++;
      cur.sum += a.score;
      byValidator.set(k, cur);
    }
    console.log("\nby validator (count / avg score):");
    for (const [addr, { count, sum }] of byValidator) {
      console.log(`  ${addr.slice(0, 10)}…  n=${count}  avg=${(sum / count).toFixed(1)}`);
    }
  }

  console.log("\n── ReputationRegistry ──");
  if (!reputationAddr) {
    console.log("(REPUTATION_REGISTRY_ADDRESS not set — skipping)");
  } else {
    const rep = new ReputationRegistryClient(reputationAddr, provider);
    const [repAvg, summary, history] = await Promise.all([
      rep.getAverageScore(agentId),
      rep.getReputationSummary(agentId),
      rep.getFeedbackHistory(agentId),
    ]);
    console.log(`getAverageScore:      ${repAvg}`);
    console.log(
      `reputation():         feedbackCount=${summary.feedbackCount} totalScore=${summary.totalScore} lastUpdated=${summary.lastUpdated}`
    );
    console.log(
      "(Reputation updates when someone calls submitFeedback — often a different bot cadence than validation.)"
    );
    const htail = history.slice(-5);
    if (htail.length) {
      console.log(`\nlast ${htail.length} feedback row(s):`);
      for (const h of htail) {
        console.log(
          `  ${h.rater.slice(0, 10)}…  score=${h.score}  type=${h.feedbackType}  "${h.comment.slice(0, 60)}${h.comment.length > 60 ? "…" : ""}"`
        );
      }
    }
  }

  console.log("\n── Local checkpoint file ──");
  console.log(
    "If run-agent cwd is erc8004:  wc -l checkpoints.jsonl   (should grow each tick)\n"
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
