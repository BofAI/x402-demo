import "dotenv/config";
import { TronWeb } from "tronweb";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import { createx402MCPClient } from "@bankofai/x402-mcp";
import { ExactTronScheme } from "@bankofai/x402-tvm/exact/client";
import { createClientTronSigner } from "./signers.js";

const TRON_PRIVATE_KEY = process.env.TRON_CLIENT_PRIVATE_KEY ?? process.env.TRON_PRIVATE_KEY;
if (!TRON_PRIVATE_KEY) {
  console.error("Error: TRON_CLIENT_PRIVATE_KEY or TRON_PRIVATE_KEY is required");
  process.exit(1);
}
const tronPrivateKey = TRON_PRIVATE_KEY;

const TRON_GRID_API_KEY = process.env.TRON_GRID_API_KEY ?? "";
const MCP_SERVER_URL = process.env.MCP_SERVER_URL ?? "http://localhost:4022";
const MCP_TOOL = process.env.MCP_TOOL ?? "get_weather";

async function main(): Promise<void> {
  const twOptions: Record<string, unknown> = {
    fullHost: "https://nile.trongrid.io",
    privateKey: tronPrivateKey,
  };
  if (TRON_GRID_API_KEY) {
    twOptions.headers = { "TRON-PRO-API-KEY": TRON_GRID_API_KEY };
  }

  const tronWeb = new TronWeb(twOptions as never);
  const signer = createClientTronSigner(tronWeb, tronPrivateKey);

  const client = createx402MCPClient({
    name: "x402-demo-mcp-client",
    version: "1.0.0",
    schemes: [{ network: "tron:nile", client: new ExactTronScheme(signer) }],
    autoPayment: true,
    onPaymentRequested: async ({ paymentRequired }) => {
      const option = paymentRequired.accepts[0];
      console.log(
        `Payment required: ${option.scheme} ${option.network} amount=${option.amount} asset=${option.asset}`,
      );
      return true;
    },
  });

  await client.connect(new SSEClientTransport(new URL(`${MCP_SERVER_URL}/sse`)));

  const ping = await client.callTool("ping");
  console.log("ping:", ping.content[0]);

  const result = await client.callTool(
    MCP_TOOL,
    { city: "Shanghai" },
    { timeout: 180_000 },
  );
  console.log("tool:", MCP_TOOL);
  console.log("paymentMade:", result.paymentMade);
  if (result.paymentResponse) {
    console.log("transaction:", result.paymentResponse.transaction);
  }
  console.log("content:", result.content[0]);

  await client.close();
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
