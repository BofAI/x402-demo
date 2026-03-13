/**
 * Test Python facilitator settle endpoint with detailed error logging
 */

import "dotenv/config";
import { TronWeb } from "tronweb";
import { x402Client } from "@bankofai/x402-core/client";
import { ExactTronScheme } from "@bankofai/x402-tvm/exact/client";

const TRON_PRIVATE_KEY = process.env.TRON_CLIENT_PRIVATE_KEY ?? process.env.TRON_PRIVATE_KEY;
const SERVER_URL = "http://localhost:8010";
const FACILITATOR_URL = "http://localhost:8011";
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
  console.log("  Python Facilitator Permit2 Settlement Test");
  console.log("═══════════════════════════════════════════════════════\n");

  const tronWeb = new TronWeb({
    fullHost: "https://nile.trongrid.io",
    privateKey: TRON_PRIVATE_KEY,
  });

  const signer = createClientTronSigner(tronWeb, TRON_PRIVATE_KEY);
  console.log(`Client Address: ${signer.address}\n`);

  // Step 1: Get payment requirements
  console.log("Step 1: Getting payment requirements...");
  const initialRes = await fetch(`${SERVER_URL}${ENDPOINT}`);
  const paymentRequired = await initialRes.json();
  console.log(`   Transfer method: ${paymentRequired.accepts[0].extra?.assetTransferMethod || "default"}`);
  console.log(`   Amount: ${paymentRequired.accepts[0].amount}`);
  console.log(`   Asset: ${paymentRequired.accepts[0].asset}\n`);

  // Step 2: Create payment payload
  console.log("Step 2: Creating payment payload...");
  const client = new x402Client();
  client.register("tron:*", new ExactTronScheme(signer));
  const paymentPayload = await client.createPaymentPayload(paymentRequired);
  
  if (!paymentPayload) {
    console.error("❌ Failed to create payment payload");
    return;
  }
  console.log("   ✅ Payment payload created\n");

  // Step 3: Verify
  console.log("Step 3: Verifying payment...");
  const verifyPayload = {
    paymentPayload,
    paymentRequirements: paymentPayload.accepted,
  };

  const verifyRes = await fetch(`${FACILITATOR_URL}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(verifyPayload),
  });

  const verifyResult = await verifyRes.json();
  console.log(`   Status: ${verifyRes.status}`);
  console.log(`   Valid: ${verifyResult.isValid}`);
  
  if (!verifyResult.isValid) {
    console.log(`   ❌ Verification failed: ${verifyResult.invalidReason}\n`);
    return;
  }
  console.log("   ✅ Verification successful\n");

  // Step 4: Settle
  console.log("Step 4: Settling payment on-chain...");
  const settleRes = await fetch(`${FACILITATOR_URL}/settle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(verifyPayload),
  });

  console.log(`   HTTP Status: ${settleRes.status}`);
  const settleResult = await settleRes.json();
  
  console.log("\nSettle Response:");
  console.log(JSON.stringify(settleResult, null, 2));
  
  if (settleResult.success) {
    console.log("\n✅ Settlement SUCCESSFUL!");
    console.log(`   Transaction: ${settleResult.transaction}`);
  } else {
    console.log("\n❌ Settlement FAILED");
    console.log(`   Error: ${settleResult.errorReason || "Unknown"}`);
    if (settleResult.detail) {
      console.log(`   Detail: ${settleResult.detail}`);
    }
  }

  console.log("\n═══════════════════════════════════════════════════════");
}

main().catch((error) => {
  console.error("\n❌ Error:", error.message);
  console.error(error);
  process.exit(1);
});
