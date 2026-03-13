/**
 * Detailed test of facilitator v2 payment verification
 * This script makes a real payment request to test the full flow
 */

import "dotenv/config";
import { TronWeb } from "tronweb";
import { x402Client } from "@bankofai/x402-core/client";
import { ExactTronScheme } from "@bankofai/x402-tron/exact/client";

// Load from x402-demo/.env
const TRON_PRIVATE_KEY = process.env.TRON_CLIENT_PRIVATE_KEY ?? process.env.TRON_PRIVATE_KEY;
const SERVER_URL = "http://localhost:8010";
const ENDPOINT = "/protected-nile";

if (!TRON_PRIVATE_KEY) {
  console.error("Error: TRON_CLIENT_PRIVATE_KEY is required");
  process.exit(1);
}

function createClientTronSigner(tronWeb: any, privateKey: string) {
  const addr = tronWeb.address.fromPrivateKey(privateKey);
  return {
    address: addr,
    async signTypedData(args: any) {
      const cleanKey = privateKey.replace(/^0x/, "");
      const sig = await tronWeb.trx._signTypedData(
        args.domain,
        args.types,
        args.message,
        cleanKey,
      );
      return sig as `0x${string}`;
    },
    async readContract(args: any) {
      const contract = await tronWeb.contract(args.abi, args.address);
      const method = contract.methods[args.functionName];
      if (!method) throw new Error(`Method ${args.functionName} not found`);
      return method(...args.args).call();
    },
  };
}

async function main() {
  console.log("═══════════════════════════════════════════════════════");
  console.log("  Detailed Facilitator v2 Payment Test");
  console.log("═══════════════════════════════════════════════════════\n");

  // Create TronWeb instance
  const tronWeb = new TronWeb({
    fullHost: "https://nile.trongrid.io",
    privateKey: TRON_PRIVATE_KEY,
  });

  const signer = createClientTronSigner(tronWeb, TRON_PRIVATE_KEY);
  console.log(`Client Address: ${signer.address}\n`);

  // Initialize x402 client
  const client = new x402Client();
  client.register("tron:*", new ExactTronScheme(signer));

  const url = `${SERVER_URL}${ENDPOINT}`;
  console.log(`Step 1: Making initial request to ${url}...`);

  // Step 1: Get 402 response
  const initialRes = await fetch(url);
  
  if (initialRes.status !== 402) {
    console.log(`\n❌ Expected 402, got ${initialRes.status}`);
    const body = await initialRes.text();
    console.log(body);
    return;
  }

  console.log("✅ Received 402 Payment Required\n");
  const paymentRequired = await initialRes.json();
  
  console.log("Payment Requirements:");
  console.log(JSON.stringify(paymentRequired, null, 2));
  console.log();

  // Step 2: Create payment payload
  console.log("Step 2: Creating payment payload...");
  const paymentPayload = await client.createPaymentPayload(paymentRequired);
  
  if (!paymentPayload) {
    console.error("❌ Failed to create payment payload");
    return;
  }

  console.log("✅ Payment payload created");
  console.log("\nPayment Payload:");
  console.log(JSON.stringify(paymentPayload, null, 2));
  console.log();

  // Step 3: Test verify endpoint directly
  console.log("Step 3: Testing facilitator /verify endpoint directly...");
  console.log(`URL: http://54.234.160.122:8001/verify\n`);

  const verifyPayload = {
    paymentPayload,
    paymentRequirements: paymentPayload.accepted,
  };

  const verifyRes = await fetch("http://54.234.160.122:8001/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(verifyPayload),
  });

  console.log(`Response Status: ${verifyRes.status}`);
  const verifyResult = await verifyRes.json();
  console.log("\nVerify Response:");
  console.log(JSON.stringify(verifyResult, null, 2));
  console.log();

  if (verifyResult.isValid) {
    console.log("✅ Payment verification successful!");
  } else {
    console.log("❌ Payment verification failed");
    console.log(`   Reason: ${verifyResult.invalidReason}`);
    if (verifyResult.invalidMessage) {
      console.log(`   Message: ${verifyResult.invalidMessage}`);
    }
  }

  console.log("\n═══════════════════════════════════════════════════════");
}

main().catch((error) => {
  console.error("\n❌ Error:", error.message);
  console.error(error);
  process.exit(1);
});
