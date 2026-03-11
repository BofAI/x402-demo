/**
 * X402 Demo Server — TypeScript / Express
 *
 * Protected resource server that returns 402 Payment Required
 * and settles payments via a facilitator.
 */

import "dotenv/config";
import express from "express";
import cors from "cors";
import { x402ResourceServer } from "@bankofai/x402-core/server";
import { HTTPFacilitatorClient } from "@bankofai/x402-core/http";
import { ExactTronScheme } from "@bankofai/x402-tron/exact/server";
import { encodePaymentRequiredHeader, decodePaymentSignatureHeader } from "@bankofai/x402-core/http";
import type { Network } from "@bankofai/x402-core/types";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PAY_TO_ADDRESS = process.env.PAY_TO_ADDRESS;
if (!PAY_TO_ADDRESS) {
  console.error("Error: PAY_TO_ADDRESS is required");
  process.exit(1);
}

const PORT = Number(process.env.SERVER_PORT ?? 8010);
const FACILITATOR_URL = process.env.FACILITATOR_URL ?? "http://localhost:8011";

function encodeToBase64(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj)).toString("base64");
}

// ---------------------------------------------------------------------------
// Endpoints configuration
// ---------------------------------------------------------------------------

interface EndpointConfig {
  path: string;
  network: Network;
  prices: Array<{ scheme: string; price: string; network: Network }>;
  label: string;
}

const ENDPOINTS: EndpointConfig[] = [
  {
    path: "/protected-nile",
    network: "tron:nile",
    prices: [
      { scheme: "exact", price: "$0.0001", network: "tron:nile" },
    ],
    label: "Nile Testnet (0.0001 USDT)",
  },
];

// ---------------------------------------------------------------------------
// Initialize resource server
// ---------------------------------------------------------------------------

const facilitatorClient = new HTTPFacilitatorClient({ url: FACILITATOR_URL });
const resourceServer = new x402ResourceServer(facilitatorClient);

// Register TRON exact scheme for the Nile demo network
const tronScheme = new ExactTronScheme();
resourceServer.register("tron:nile", tronScheme);

// ---------------------------------------------------------------------------
// Express app
// ---------------------------------------------------------------------------

const app = express();
app.use(cors());
app.use(express.json());

let requestCount = 0;

app.get("/", (_req, res) => {
  res.json({
    service: "X402 Protected Resource Server (TypeScript)",
    status: "running",
    payTo: PAY_TO_ADDRESS,
    facilitator: FACILITATOR_URL,
    endpoints: ENDPOINTS.map((e) => ({ path: e.path, label: e.label })),
  });
});

// ---------------------------------------------------------------------------
// Payment-protected endpoints
// ---------------------------------------------------------------------------

async function initServer() {
  try {
    await resourceServer.initialize();
    console.log("[server] Synced with facilitator");
  } catch (e: any) {
    console.warn(`[server] Could not sync with facilitator: ${e.message}`);
    console.warn("[server] Will retry on first request");
  }

  for (const endpoint of ENDPOINTS) {
    const paymentOptions = endpoint.prices.map((p) => ({
      scheme: p.scheme,
      price: p.price,
      network: p.network,
      payTo: PAY_TO_ADDRESS!,
      maxTimeoutSeconds: 300,
    }));

    app.get(endpoint.path, async (req, res) => {
      try {
        const requirements = await resourceServer.buildPaymentRequirementsFromOptions(
          paymentOptions,
          {},
        );

        // Check for payment header: v2 (PAYMENT-SIGNATURE), v1 (X-PAYMENT), or manual (x-402-payment)
        const paymentHeader =
          (req.headers["payment-signature"] as string | undefined) ??
          (req.headers["x-payment"] as string | undefined) ??
          (req.headers["x-402-payment"] as string | undefined);

        if (!paymentHeader) {
          const paymentRequired = await resourceServer.createPaymentRequiredResponse(
            requirements,
            { url: endpoint.path, description: endpoint.label, mimeType: "application/json" },
          );
          res.setHeader("PAYMENT-REQUIRED", encodePaymentRequiredHeader(paymentRequired));
          res.status(402).json(paymentRequired);
          return;
        }

        // Decode payment (v2 PAYMENT-SIGNATURE is base64-encoded PaymentPayload)
        const paymentPayload = decodePaymentSignatureHeader(paymentHeader);

        // Find matching requirement
        const matchedReq = resourceServer.findMatchingRequirements(requirements, paymentPayload);
        if (!matchedReq) {
          res.status(400).json({ error: "No matching payment requirement" });
          return;
        }

        // Verify
        const verifyResult = await resourceServer.verifyPayment(paymentPayload, matchedReq);
        if (!verifyResult.isValid) {
          res.status(402).json({ error: "Payment verification failed", details: verifyResult });
          return;
        }

        // Protected content
        requestCount++;
        const responseBody = {
          message: `Access granted! (request #${requestCount})`,
          network: endpoint.network,
          endpoint: endpoint.path,
          timestamp: new Date().toISOString(),
        };

        // Settle
        const settleResult = await resourceServer.settlePayment(paymentPayload, matchedReq);

        // Add settlement header
        res.setHeader("payment-response", encodeToBase64(settleResult));
        res.json(responseBody);
      } catch (e: any) {
        console.error(`[${endpoint.path}] Error:`, e.message);
        res.status(500).json({ error: e.message });
      }
    });

    console.log(`[server] Registered: GET ${endpoint.path} — ${endpoint.label}`);
  }
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

initServer().then(() => {
  app.listen(PORT, "0.0.0.0", () => {
    console.log("=".repeat(60));
    console.log("X402 Protected Resource Server (TypeScript) — Started");
    console.log("=".repeat(60));
    console.log(`  Port:        ${PORT}`);
    console.log(`  Pay To:      ${PAY_TO_ADDRESS}`);
    console.log(`  Facilitator: ${FACILITATOR_URL}`);
    console.log("=".repeat(60));
  });
});
