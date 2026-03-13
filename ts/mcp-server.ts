import "dotenv/config";
import express from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { HTTPFacilitatorClient, x402ResourceServer } from "@bankofai/x402-core/server";
import { ExactTronScheme } from "@bankofai/x402-tron/exact/server";
import { createPaymentWrapper } from "@bankofai/x402-mcp";
import { z } from "zod";

const PAY_TO_ADDRESS = process.env.PAY_TO_ADDRESS;
if (!PAY_TO_ADDRESS) {
  console.error("Error: PAY_TO_ADDRESS is required");
  process.exit(1);
}
const payToAddress = PAY_TO_ADDRESS;

const FACILITATOR_URL = process.env.FACILITATOR_URL ?? "http://localhost:8001";
const PORT = Number(process.env.MCP_PORT ?? 4022);
const FACILITATOR_RETRY_MS = Number(process.env.FACILITATOR_RETRY_MS ?? 3000);

function getWeatherData(city: string): { city: string; weather: string; temperature: number } {
  const conditions = ["sunny", "cloudy", "rainy", "windy"];
  const weather = conditions[Math.floor(Math.random() * conditions.length)];
  const temperature = Math.floor(Math.random() * 15) + 20;
  return { city, weather, temperature };
}

async function main(): Promise<void> {
  const facilitatorClient = new HTTPFacilitatorClient({ url: FACILITATOR_URL });
  const resourceServer = new x402ResourceServer(facilitatorClient);
  resourceServer.register("tron:nile", new ExactTronScheme());
  while (true) {
    try {
      await resourceServer.initialize();
      console.log("[mcp] Synced with facilitator");
      break;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`[mcp] Facilitator not ready: ${message}`);
      console.warn(`[mcp] Retrying in ${FACILITATOR_RETRY_MS}ms...`);
      await new Promise(resolve => setTimeout(resolve, FACILITATOR_RETRY_MS));
    }
  }

  const accepts = await resourceServer.buildPaymentRequirements({
    scheme: "exact",
    network: "tron:nile",
    payTo: payToAddress,
    price: "$0.0001",
  });

  const paid = createPaymentWrapper(resourceServer, { accepts });

  const mcpServer = new McpServer({
    name: "x402-demo-mcp",
    version: "1.0.0",
  });

  mcpServer.tool("ping", "Free health check", {}, async () => ({
    content: [{ type: "text", text: "pong" }],
  }));

  mcpServer.tool(
    "get_weather",
    "Paid weather tool on TRON Nile via x402 exact.",
    { city: z.string().describe("The city name to query") },
    paid(async (args: { city: string }) => ({
      content: [{ type: "text", text: JSON.stringify(getWeatherData(args.city)) }],
    })),
  );

  const app = express();
  const transports = new Map<string, SSEServerTransport>();

  app.get("/health", (_req, res) => {
    res.json({
      status: "ok",
      transport: "sse",
      tools: ["ping", "get_weather"],
      facilitator: FACILITATOR_URL,
    });
  });

  app.get("/sse", async (_req, res) => {
    const transport = new SSEServerTransport("/messages", res);
    const sessionId = crypto.randomUUID();
    transports.set(sessionId, transport);
    res.on("close", () => {
      transports.delete(sessionId);
    });
    await mcpServer.connect(transport);
  });

  app.post("/messages", express.json(), async (req, res) => {
    const transport = Array.from(transports.values())[0];
    if (!transport) {
      res.status(400).json({ error: "No active SSE connection" });
      return;
    }
    await transport.handlePostMessage(req, res, req.body);
  });

  app.listen(PORT, "0.0.0.0", () => {
    console.log("=".repeat(60));
    console.log("X402 MCP Server (TypeScript) — Started");
    console.log("=".repeat(60));
    console.log(`  Port:        ${PORT}`);
    console.log(`  Facilitator: ${FACILITATOR_URL}`);
    console.log(`  Pay To:      ${payToAddress}`);
    console.log(`  SSE:         http://localhost:${PORT}/sse`);
    console.log(`  Health:      http://localhost:${PORT}/health`);
    console.log("=".repeat(60));
  });
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
