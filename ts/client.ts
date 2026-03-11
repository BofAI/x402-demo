/**
 * X402 Demo Client — TypeScript
 *
 * Registers TRON exact scheme (TIP-712 / Permit2) and makes
 * a payment-protected request to the demo server.
 */

import "dotenv/config";
import { TronWeb } from "tronweb";
import { x402Client } from "@bankofai/x402-core/client";
import { safeBase64Decode } from "@bankofai/x402-core/utils";
import { ExactTronScheme } from "@bankofai/x402-tron/exact/client";
import { createClientTronSigner } from "./signers.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const TRON_PRIVATE_KEY = process.env.TRON_CLIENT_PRIVATE_KEY ?? process.env.TRON_PRIVATE_KEY;
if (!TRON_PRIVATE_KEY) {
  console.error("Error: TRON_CLIENT_PRIVATE_KEY or TRON_PRIVATE_KEY is required");
  process.exit(1);
}

const SERVER_URL = process.env.SERVER_URL ?? "http://localhost:8010";
const ENDPOINT = process.env.ENDPOINT ?? "/protected-nile";
const TRON_GRID_API_KEY = process.env.TRON_GRID_API_KEY ?? "";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const hr = () => console.log("─".repeat(60));

function decodeBase64Json<T = any>(encoded: string): T {
  return JSON.parse(safeBase64Decode(encoded)) as T;
}

function encodeBase64Json(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj)).toString("base64");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const tronPrivateKey = TRON_PRIVATE_KEY as string;

  // Create TronWeb instance
  const twOptions: any = { fullHost: "https://nile.trongrid.io", privateKey: tronPrivateKey };
  if (TRON_GRID_API_KEY) twOptions.headers = { "TRON-PRO-API-KEY": TRON_GRID_API_KEY };
  const tw = new TronWeb(twOptions);

  // Create client signer
  const signer = createClientTronSigner(tw, tronPrivateKey);

  hr();
  console.log("X402 Client (TypeScript · New SDK)");
  hr();
  console.log(`  TRON Address: ${signer.address}`);
  console.log(`  Target:       ${SERVER_URL}${ENDPOINT}`);
  hr();

  // Initialize x402 client
  const client = new x402Client();
  client.register("tron:*", new ExactTronScheme(signer));

  const url = `${SERVER_URL}${ENDPOINT}`;
  console.log(`\nGET ${url} ...`);

  // Step 1: Make initial request
  const initialRes = await fetch(url);

  if (initialRes.status !== 402) {
    console.log(`\nResponse: ${initialRes.status} ${initialRes.statusText}`);
    const body = await initialRes.text();
    console.log(body.slice(0, 500));
    return;
  }

  console.log("\n402 Payment Required received");
  const paymentRequired = await initialRes.json() as any;

  // Step 2: Select and create payment
  const accepts = paymentRequired.accepts as any[];
  console.log(`  Accepts: ${accepts.length} option(s)`);
  for (const a of accepts) {
    console.log(`    - scheme=${a.scheme} network=${a.network} amount=${a.amount} asset=${a.asset}`);
  }

  // Use x402Client to create payment payload
  // createPaymentPayload expects the full PaymentRequired object
  const paymentPayload = await client.createPaymentPayload(paymentRequired);
  if (!paymentPayload) {
    console.error("\nFailed to create payment payload");
    process.exit(1);
  }

  console.log(`\nPayment created: scheme=${paymentPayload.accepted.scheme} network=${paymentPayload.accepted.network}`);

  // Step 3: Replay request with payment
  const encoded = encodeBase64Json(paymentPayload);
  const payRes = await fetch(url, {
    headers: { "x-402-payment": encoded },
  });

  console.log(`\n${payRes.status} ${payRes.statusText}`);

  // Check settlement header
  const paymentResponseHeader = payRes.headers.get("payment-response");
  if (paymentResponseHeader) {
    try {
      const settle = decodeBase64Json(paymentResponseHeader);
      console.log("\nSettlement:");
      console.log(`  success:     ${settle.success}`);
      console.log(`  network:     ${settle.network}`);
      console.log(`  transaction: ${settle.transaction}`);
      if (settle.errorReason) console.log(`  error:       ${settle.errorReason}`);
    } catch {
      console.log("\nPayment-Response header:", paymentResponseHeader);
    }
  }

  // Print response body
  const ct = payRes.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    const body = await payRes.json();
    console.log(`\n${JSON.stringify(body, null, 2)}`);
  } else {
    const text = await payRes.text();
    console.log(`\n${text.slice(0, 500)}`);
  }
}

main().catch((err) => {
  console.error("\n", err instanceof Error ? err.message : err);
  process.exit(1);
});
