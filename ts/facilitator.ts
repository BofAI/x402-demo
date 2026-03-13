/**
 * X402 Demo Facilitator — TypeScript / Express
 *
 * Verifies TIP-712 / Permit2 signatures and settles payments on-chain.
 * Scoped to TRON Nile for the demo.
 */

import "dotenv/config";
import express from "express";
import cors from "cors";
import { TronWeb } from "tronweb";
import { createPublicClient, createWalletClient, http } from "viem";
import { bscTestnet } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";
import { x402Facilitator } from "@bankofai/x402-core/facilitator";
import { toFacilitatorEvmSigner } from "@bankofai/x402-evm";
import { ExactEvmScheme as ExactEvmFacilitatorScheme } from "@bankofai/x402-evm/exact/facilitator";
import { ExactTronScheme } from "@bankofai/x402-tron/exact/facilitator";
import { createFacilitatorTronSigner } from "./signers.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const TRON_PRIVATE_KEY = process.env.TRON_FACILITATOR_PRIVATE_KEY ?? process.env.TRON_PRIVATE_KEY;
if (!TRON_PRIVATE_KEY) {
  console.error("Error: TRON_FACILITATOR_PRIVATE_KEY or TRON_PRIVATE_KEY is required");
  process.exit(1);
}

const PORT = Number(process.env.FACILITATOR_PORT ?? 8001);
const TRON_GRID_API_KEY = process.env.TRON_GRID_API_KEY ?? "";
const BSC_FACILITATOR_PRIVATE_KEY = process.env.BSC_FACILITATOR_PRIVATE_KEY;
const BSC_TESTNET_RPC_URL = process.env.BSC_TESTNET_RPC_URL;

const TRON_NETWORKS = [
  { name: "nile", fullHost: "https://nile.trongrid.io" },
] as const;

function normalizeHexPrivateKey(privateKey: string): `0x${string}` {
  return (privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`) as `0x${string}`;
}

let evmTxQueue: Promise<void> = Promise.resolve();

async function enqueueEvmTransaction<T>(operation: () => Promise<T>): Promise<T> {
  const queued = evmTxQueue.then(operation, operation);
  evmTxQueue = queued.then(
    () => undefined,
    () => undefined,
  );
  return queued;
}

// ---------------------------------------------------------------------------
// Initialize facilitator
// ---------------------------------------------------------------------------

const facilitator = new x402Facilitator();

for (const net of TRON_NETWORKS) {
  const twOptions: any = { fullHost: net.fullHost, privateKey: TRON_PRIVATE_KEY };
  if (TRON_GRID_API_KEY) twOptions.headers = { "TRON-PRO-API-KEY": TRON_GRID_API_KEY };

  const tw = new TronWeb(twOptions);
  const signer = createFacilitatorTronSigner(tw, TRON_PRIVATE_KEY);

  facilitator.register(`tron:${net.name}`, new ExactTronScheme(signer));
  console.log(`[facilitator] Registered exact scheme for tron:${net.name}`);
}

if (BSC_FACILITATOR_PRIVATE_KEY && BSC_TESTNET_RPC_URL) {
  const account = privateKeyToAccount(normalizeHexPrivateKey(BSC_FACILITATOR_PRIVATE_KEY));
  const publicClient = createPublicClient({
    chain: bscTestnet,
    transport: http(BSC_TESTNET_RPC_URL),
  });
  const walletClient = createWalletClient({
    account,
    chain: bscTestnet,
    transport: http(BSC_TESTNET_RPC_URL),
  });

  const signer = toFacilitatorEvmSigner({
    address: account.address,
    getCode: args => publicClient.getCode(args),
    readContract: args =>
      publicClient.readContract({
        ...args,
        args: args.args || [],
      } as never),
    verifyTypedData: args => publicClient.verifyTypedData(args as never),
    writeContract: async (args) => {
      try {
        return await enqueueEvmTransaction(() =>
          walletClient.writeContract({
            ...args,
            args: args.args || [],
          } as never),
        );
      } catch (error) {
        console.error("[bsc/writeContract] FAILED:", error);
        throw error;
      }
    },
    sendTransaction: async (args) => {
      try {
        return await enqueueEvmTransaction(() => walletClient.sendTransaction(args));
      } catch (error) {
        console.error("[bsc/sendTransaction] FAILED:", error);
        throw error;
      }
    },
    waitForTransactionReceipt: async (args) => {
      try {
        return await publicClient.waitForTransactionReceipt(args);
      } catch (error) {
        console.error("[bsc/waitForTransactionReceipt] FAILED:", error);
        throw error;
      }
    },
  });

  facilitator.register("eip155:97", new ExactEvmFacilitatorScheme(signer));
  console.log("[facilitator] Registered exact scheme for eip155:97");
}

// Lifecycle hooks for logging
facilitator
  .onBeforeVerify(async (ctx) => {
    console.log(`[verify] scheme=${ctx.requirements.scheme} network=${ctx.requirements.network}`);
  })
  .onAfterVerify(async (ctx) => {
    console.log(`[verify] result: isValid=${ctx.result.isValid}`);
  })
  .onVerifyFailure(async (ctx) => {
    console.error(`[verify] FAILED:`, ctx.error.message);
  })
  .onBeforeSettle(async (ctx) => {
    console.log(`[settle] scheme=${ctx.requirements.scheme} network=${ctx.requirements.network}`);
  })
  .onAfterSettle(async (ctx) => {
    console.log(`[settle] result: success=${ctx.result.success} tx=${ctx.result.transaction}`);
  })
  .onSettleFailure(async (ctx) => {
    console.error(`[settle] FAILED:`, ctx.error.message);
  });

// ---------------------------------------------------------------------------
// Express app
// ---------------------------------------------------------------------------

const app = express();
app.use(cors());
app.use(express.json({ limit: "1mb" }));

app.get("/", (_req, res) => {
  res.json({ service: "X402 Facilitator (TypeScript)", status: "running" });
});

app.get("/supported", async (_req, res) => {
  try {
    const supported = await facilitator.getSupported();
    res.json(supported);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/verify", async (req, res) => {
  try {
    const { paymentPayload, paymentRequirements } = req.body;
    const result = await facilitator.verify(paymentPayload, paymentRequirements);
    res.json(result);
  } catch (e: any) {
    console.error("[verify] Error:", e.message);
    res.status(500).json({ error: e.message });
  }
});

app.post("/settle", async (req, res) => {
  try {
    const { paymentPayload, paymentRequirements } = req.body;
    const result = await facilitator.settle(paymentPayload, paymentRequirements);
    res.json(result);
  } catch (e: any) {
    console.error("[settle] Error:", e.message);
    res.status(500).json({ error: e.message });
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

app.listen(PORT, "0.0.0.0", () => {
  console.log("=".repeat(60));
  console.log("X402 Facilitator (TypeScript) — Started");
  console.log("=".repeat(60));
  console.log(`  Port:     ${PORT}`);
  const networks = [...TRON_NETWORKS.map((n) => `tron:${n.name}`)];
  if (BSC_FACILITATOR_PRIVATE_KEY && BSC_TESTNET_RPC_URL) {
    networks.push("eip155:97");
  }
  console.log(`  Networks: ${networks.join(", ")}`);
  console.log("  Endpoints:");
  console.log(`    GET  http://0.0.0.0:${PORT}/supported`);
  console.log(`    POST http://0.0.0.0:${PORT}/verify`);
  console.log(`    POST http://0.0.0.0:${PORT}/settle`);
  console.log("=".repeat(60));
});
