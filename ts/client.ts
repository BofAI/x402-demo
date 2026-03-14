/**
 * X402 Demo Client — TypeScript
 *
 * Registers TRON exact scheme (TIP-712 / Permit2) and makes
 * a payment-protected request to the demo server.
 */

import "dotenv/config";
import { TronWeb } from "tronweb";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { x402Client } from "@bankofai/x402-core/client";
import { encodePaymentSignatureHeader } from "@bankofai/x402-core/http";
import { safeBase64Decode } from "@bankofai/x402-core/utils";
import {
  createPermit2ApprovalTx as createEvmPermit2ApprovalTx,
  getPermit2AllowanceReadParams as getEvmPermit2AllowanceReadParams,
  toClientEvmSigner,
} from "@bankofai/x402-evm";
import { ExactEvmScheme } from "@bankofai/x402-evm/exact/client";
import {
  createPermit2ApprovalTx as createTronPermit2ApprovalTx,
  getPermit2AllowanceReadParams as getTronPermit2AllowanceReadParams,
  ExactTronScheme,
  PERMIT2_ADDRESSES as TRON_PERMIT2_ADDRESSES,
} from "@bankofai/x402-tron";
import { createPublicClient, createWalletClient, http } from "viem";
import { bscTestnet } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";
import { createClientTronSigner } from "./signers.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const TRON_PRIVATE_KEY = process.env.TRON_CLIENT_PRIVATE_KEY ?? process.env.TRON_PRIVATE_KEY;
if (!TRON_PRIVATE_KEY) {
  console.error("Error: TRON_CLIENT_PRIVATE_KEY or TRON_PRIVATE_KEY is required");
  process.exit(1);
}

const SERVER_URL = process.env.SERVER_URL ?? "http://localhost:8000";
const ENDPOINT = process.env.ENDPOINT ?? "/protected-nile";
const TRON_GRID_API_KEY = process.env.TRON_GRID_API_KEY ?? "";
const BSC_CLIENT_PRIVATE_KEY = process.env.BSC_CLIENT_PRIVATE_KEY;
const BSC_TESTNET_RPC_URL = process.env.BSC_TESTNET_RPC_URL;
const PREFERRED_NETWORK = process.env.PREFERRED_NETWORK;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const hr = () => console.log("─".repeat(60));
const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

function normalizeHexPrivateKey(privateKey: string): `0x${string}` {
  return (privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`) as `0x${string}`;
}

function decodeBase64Json<T = any>(encoded: string): T {
  return JSON.parse(safeBase64Decode(encoded)) as T;
}

async function saveImage(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  const ext = contentType.includes("jpeg") || contentType.includes("jpg")
    ? "jpg"
    : contentType.includes("webp")
      ? "webp"
      : "png";
  const imageBuffer = Buffer.from(await response.arrayBuffer());
  const outputPath = join(tmpdir(), `x402_${Date.now()}.${ext}`);
  writeFileSync(outputPath, imageBuffer);
  return outputPath;
}

function extractTronBroadcastTransactionId(result: { txid?: string; transaction?: { txID?: string } }): string {
  const txid = result.txid ?? result.transaction?.txID;
  if (!txid) {
    throw new Error("TRON approval broadcast did not return a transaction id");
  }
  return txid;
}

async function waitForTronTransaction(tronWeb: TronWeb, hash: string): Promise<void> {
  void tronWeb;
  void hash;
  await new Promise((resolve) => setTimeout(resolve, 6000));
}

async function ensureTronPermit2Approval(args: {
  tronWeb: TronWeb;
  ownerAddress: string;
  requirement: any;
}): Promise<void> {
  const { tronWeb, ownerAddress, requirement } = args;
  if (requirement.extra?.assetTransferMethod !== "permit2") {
    return;
  }

  const readParams = getTronPermit2AllowanceReadParams({
    tokenAddress: requirement.asset,
    ownerAddress,
    network: requirement.network,
  });
  const contract = await tronWeb.contract().at(readParams.address);
  const allowance = BigInt((await contract.allowance(...readParams.args).call()).toString());
  const required = BigInt(requirement.amount);
  if (allowance >= required) {
    return;
  }

  const spender = TRON_PERMIT2_ADDRESSES[requirement.network];
  if (!spender) {
    throw new Error(`No TRON Permit2 configured for ${requirement.network}`);
  }

  console.log(`\nAuto-approving TRON Permit2: ${allowance.toString()} < ${required.toString()}`);
  createTronPermit2ApprovalTx(requirement.asset, requirement.network);
  const approval = await tronWeb.transactionBuilder.triggerSmartContract(
    requirement.asset,
    "approve(address,uint256)",
    {
      feeLimit: 1_000_000_000,
      callValue: 0,
    },
    [
      { type: "address", value: spender },
      { type: "uint256", value: MAX_UINT256.toString() },
    ],
    ownerAddress,
  );
  const signed = await tronWeb.trx.sign(approval.transaction);
  const sent = await tronWeb.trx.sendRawTransaction(signed);
  const txid = extractTronBroadcastTransactionId(sent as { txid?: string; transaction?: { txID?: string } });
  console.log(`  approval tx: ${txid}`);
  await waitForTronTransaction(tronWeb, txid);
}

async function ensureEvmPermit2Approval(args: {
  publicClient: ReturnType<typeof createPublicClient>;
  walletClient: ReturnType<typeof createWalletClient>;
  account: ReturnType<typeof privateKeyToAccount>;
  requirement: any;
}): Promise<void> {
  const { publicClient, walletClient, account, requirement } = args;
  if (requirement.extra?.assetTransferMethod !== "permit2") {
    return;
  }

  const readParams = getEvmPermit2AllowanceReadParams({
    tokenAddress: requirement.asset as `0x${string}`,
    ownerAddress: account.address,
    network: requirement.network,
  });
  const allowance = await publicClient.readContract(readParams);
  const required = BigInt(requirement.amount);
  if (allowance >= required) {
    return;
  }

  console.log(`\nAuto-approving EVM Permit2: ${allowance.toString()} < ${required.toString()}`);
  const approvalTx = createEvmPermit2ApprovalTx(requirement.asset as `0x${string}`, requirement.network);
  const txHash = await walletClient.sendTransaction({
    account,
    chain: bscTestnet,
    to: approvalTx.to,
    data: approvalTx.data,
  });
  console.log(`  approval tx: ${txHash}`);
  await publicClient.waitForTransactionReceipt({ hash: txHash });
}

function selectPaymentRequirements(preferredNetwork?: string) {
  return (_x402Version: number, accepts: any[]) => {
    if (!accepts.length) {
      throw new Error("No payment requirements available");
    }

    if (preferredNetwork) {
      const preferred = accepts.find((req) => req.network === preferredNetwork);
      if (preferred) {
        return preferred;
      }

      console.warn(`Preferred network ${preferredNetwork} not found in accepts; falling back to first option.`);
    }

    return accepts[0];
  };
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
  const ownerTronAddress = signer.address;
  let evmAccount: ReturnType<typeof privateKeyToAccount> | undefined;
  let publicClient: ReturnType<typeof createPublicClient> | undefined;
  let walletClient: ReturnType<typeof createWalletClient> | undefined;

  hr();
  console.log("X402 Client (TypeScript · New SDK)");
  hr();
  console.log(`  TRON Address: ${signer.address}`);
  if (BSC_CLIENT_PRIVATE_KEY && BSC_TESTNET_RPC_URL) {
    evmAccount = privateKeyToAccount(normalizeHexPrivateKey(BSC_CLIENT_PRIVATE_KEY));
    publicClient = createPublicClient({
      chain: bscTestnet,
      transport: http(BSC_TESTNET_RPC_URL),
    });
    walletClient = createWalletClient({
      chain: bscTestnet,
      transport: http(BSC_TESTNET_RPC_URL),
      account: evmAccount,
    });
    console.log(`  BSC Address:  ${evmAccount.address}`);
  }
  if (PREFERRED_NETWORK) {
    console.log(`  Preferred:    ${PREFERRED_NETWORK}`);
  }
  console.log(`  Target:       ${SERVER_URL}${ENDPOINT}`);
  hr();

  // Initialize x402 client
  const client = new x402Client(selectPaymentRequirements(PREFERRED_NETWORK));
  client.register("tron:*", new ExactTronScheme(signer));
  if (evmAccount && publicClient) {
    client.register("eip155:*", new ExactEvmScheme(toClientEvmSigner(evmAccount, publicClient)));
  }

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
  const selected =
    (PREFERRED_NETWORK
      ? accepts.find((req) => req.network === PREFERRED_NETWORK)
      : undefined) ?? accepts[0];
  if (selected?.network?.startsWith("tron:")) {
    await ensureTronPermit2Approval({
      tronWeb: tw,
      ownerAddress: ownerTronAddress,
      requirement: selected,
    });
  } else if (selected?.network?.startsWith("eip155:") && evmAccount && publicClient && walletClient) {
    await ensureEvmPermit2Approval({
      publicClient,
      walletClient,
      account: evmAccount,
      requirement: selected,
    });
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
  const payRes = await fetch(url, {
    headers: { "PAYMENT-SIGNATURE": encodePaymentSignatureHeader(paymentPayload) },
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
  } else if (ct.includes("image/")) {
    const imagePath = await saveImage(payRes);
    console.log(`\nImage saved → ${imagePath}`);
  } else {
    const text = await payRes.text();
    console.log(`\n${text.slice(0, 500)}`);
  }
}

main().catch((err) => {
  console.error("\n", err instanceof Error ? err.message : err);
  process.exit(1);
});
