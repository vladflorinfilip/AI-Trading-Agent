import * as dotenv from "dotenv";
dotenv.config();

import { ethers } from "ethers";

const rpcUrl = process.env.SEPOLIA_RPC_URL!;
const privateKey = process.env.PRIVATE_KEY!;
const vaultAddress = process.env.HACKATHON_VAULT_ADDRESS!;
const agentId = parseInt(process.env.AGENT_ID || "0");

const VAULT_ABI = [
  "function claimAllocation(uint256 agentId) external",
  "function getBalance(uint256 agentId) external view returns (uint256)",
  "function allocatedCapital(uint256 agentId) external view returns (uint256)",
];

async function main() {
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const signer = new ethers.Wallet(privateKey, provider);
  const vault = new ethers.Contract(vaultAddress, VAULT_ABI, signer);

  console.log(`Claiming allocation for agentId: ${agentId}`);
  console.log(`Vault: ${vaultAddress}`);
  console.log(`Wallet: ${signer.address}\n`);

  try {
    const tx = await vault.claimAllocation(agentId);
    console.log(`Tx sent: ${tx.hash}`);
    const receipt = await tx.wait();
    console.log(`Confirmed in block ${receipt.blockNumber}`);

    const balance = await vault.getBalance(agentId);
    console.log(`\nAgent ${agentId} vault balance: ${ethers.formatEther(balance)} ETH`);
  } catch (err: any) {
    if (err.reason) {
      console.error(`Failed: ${err.reason}`);
    } else {
      console.error(err);
    }
  }
}

main();
