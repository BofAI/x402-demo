/**
 * X402 Demo — TypeScript Protected Resource Server (Hono)
 *
 * TypeScript port of `server/main.py`. Serves a payment-protected image
 * endpoint. Uses:
 *   - x402Hono   (Hono middleware — takes `{ facilitator, accepts }`)
 *   - FacilitatorClient (talks to the facilitator service at FACILITATOR_URL)
 *
 * Run:
 *   SERVER_PORT=8000 tsx src/main.ts
 */

import { serve } from '@hono/node-server';
import { config } from 'dotenv';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { readFileSync, existsSync } from 'fs';

import {
  FacilitatorClient,
  x402Hono,
  getNetworkTokens,
  getPaymentPermitAddress,
  NETWORKS,
  parsePrice,
} from '@bankofai/x402';

// ---------------------------------------------------------------------------
// Env
// ---------------------------------------------------------------------------
const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, '../../.env') });

const PAY_TO_ADDRESS     = process.env.PAY_TO_ADDRESS ?? '';
const BSC_PAY_TO_ADDRESS = process.env.BSC_PAY_TO_ADDRESS ?? '';
const FACILITATOR_URL    = process.env.FACILITATOR_URL ?? 'http://localhost:8001';
const FACILITATOR_API_KEY = process.env.FACILITATOR_API_KEY ?? '';
const SERVER_HOST        = process.env.SERVER_HOST ?? '0.0.0.0';
const SERVER_PORT        = parseInt(process.env.SERVER_PORT ?? '8000', 10);

// GasFree enable flags
const gasfreeEnabledNile    = (process.env.GASFREE_ENABLED_NILE    ?? 'true') !== 'false';
const gasfreeEnabledShasta  = (process.env.GASFREE_ENABLED_SHASTA  ?? 'true') !== 'false';
const gasfreeEnabledMainnet = (process.env.GASFREE_ENABLED_MAINNET ?? 'true') !== 'false';

if (!PAY_TO_ADDRESS) {
  console.error('❌  PAY_TO_ADDRESS is required');
  process.exit(1);
}
if (!isTronAddress(PAY_TO_ADDRESS)) {
  console.error(`❌  PAY_TO_ADDRESS must be a TRON Base58 address for TRON endpoints: ${PAY_TO_ADDRESS}`);
  process.exit(1);
}
if (BSC_PAY_TO_ADDRESS && !isEvmAddress(BSC_PAY_TO_ADDRESS)) {
  console.error(`❌  BSC_PAY_TO_ADDRESS must be an EVM 0x address for BSC endpoints: ${BSC_PAY_TO_ADDRESS}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// FacilitatorClient — mirrors Python's FacilitatorClient
// ---------------------------------------------------------------------------
const facilitatorHeaders: Record<string, string> = FACILITATOR_API_KEY
  ? { 'X-API-KEY': FACILITATOR_API_KEY }
  : {};
const facilitator = new FacilitatorClient({ baseUrl: FACILITATOR_URL, headers: facilitatorHeaders });

// ---------------------------------------------------------------------------
// Helpers — build PaymentRequirements accepts[] from price strings
// ---------------------------------------------------------------------------
async function buildAccepts(
  priceSchemes: Array<{ price: string; scheme: string; network: string; payTo: string }>,
) {
  const accepts = [];
  for (const { price, scheme, network, payTo } of priceSchemes) {
    const parsed = parsePrice(price, network);
    accepts.push({
      scheme,
      network,
      asset: parsed.asset,
      amount: parsed.amount,
      payTo,
    });
  }
  return accepts;
}

function isTronAddress(address: string): boolean {
  return /^T[1-9A-HJ-NP-Za-km-z]{33}$/.test(address);
}

function isEvmAddress(address: string): boolean {
  return /^0x[a-fA-F0-9]{40}$/.test(address);
}

// ---------------------------------------------------------------------------
// Print startup config
// ---------------------------------------------------------------------------
const allNetworks = [NETWORKS.TRON_NILE, NETWORKS.TRON_SHASTA, NETWORKS.TRON_MAINNET, NETWORKS.BSC_TESTNET, NETWORKS.BSC_MAINNET];

console.log('='.repeat(80));
console.log('X402 Protected Resource Server (TypeScript/Hono) — Configuration');
console.log('='.repeat(80));
console.log(`Pay To Address : ${PAY_TO_ADDRESS}`);
if (BSC_PAY_TO_ADDRESS) console.log(`BSC Pay To    : ${BSC_PAY_TO_ADDRESS}`);
console.log(`Facilitator URL: ${FACILITATOR_URL}`);
console.log(`Facilitator API: ${FACILITATOR_API_KEY ? '**configured**' : '(not set)'}`);
console.log(`GasFree Nile   : ${gasfreeEnabledNile}`);
console.log(`GasFree Shasta : ${gasfreeEnabledShasta}`);
console.log(`GasFree Mainnet: ${gasfreeEnabledMainnet}`);
console.log('\nRegistered Networks:');
for (const net of allNetworks) {
  const tokens = getNetworkTokens(net);
  const permit = getPaymentPermitAddress(net);
  console.log(`  ${net}:`);
  console.log(`    PaymentPermit: ${permit}`);
  for (const [symbol, info] of Object.entries(tokens)) {
    console.log(`    ${symbol}: ${info.address} (decimals=${info.decimals})`);
  }
}
console.log('='.repeat(80));

// ---------------------------------------------------------------------------
// Protected image helper
// ---------------------------------------------------------------------------
const PROTECTED_IMAGE_PATH = resolve(__dirname, '../../server/protected.png');
let requestCount = 0;

function getProtectedImageBytes(): ArrayBuffer {
  if (!existsSync(PROTECTED_IMAGE_PATH)) {
    throw new Error(`Protected image not found: ${PROTECTED_IMAGE_PATH}`);
  }
  const buf = readFileSync(PROTECTED_IMAGE_PATH);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

// ---------------------------------------------------------------------------
// Hono app
// ---------------------------------------------------------------------------
const app = new Hono();

app.use('*', cors({ origin: '*', exposeHeaders: ['*'] }));

// Health check
app.get('/', (c) =>
  c.json({
    service: 'X402 Protected Resource Server (TypeScript)',
    status: 'running',
    pay_to: PAY_TO_ADDRESS,
    facilitator: FACILITATOR_URL,
  }),
);

// ---------------------------------------------------------------------------
// Protected endpoints
// Nile testnet (exact_permit + optional gasfree)
// ---------------------------------------------------------------------------

const nilePriceSchemes: Array<{ price: string; scheme: string; network: string; payTo: string }> = [
  { price: '0.0001 USDT', scheme: 'exact_permit',  network: NETWORKS.TRON_NILE, payTo: PAY_TO_ADDRESS },
  { price: '0.0001 USDD', scheme: 'exact_permit',  network: NETWORKS.TRON_NILE, payTo: PAY_TO_ADDRESS },
];
if (gasfreeEnabledNile) {
  nilePriceSchemes.push({ price: '0.0001 USDT', scheme: 'exact_gasfree', network: NETWORKS.TRON_NILE, payTo: PAY_TO_ADDRESS });
}
const nileAccepts = await buildAccepts(nilePriceSchemes);

app.get(
  '/protected-nile',
  x402Hono({ facilitator, accepts: nileAccepts }),
  async (c) => {
    const count = ++requestCount;
    console.log(`[Nile] Serving protected image (req #${count})`);
    return new Response(getProtectedImageBytes(), {
      headers: { 'Content-Type': 'image/png' },
    });
  },
);

// Shasta testnet
const shastaPriceSchemes: Array<{ price: string; scheme: string; network: string; payTo: string }> = [
  { price: '0.0001 USDT', scheme: 'exact_permit', network: NETWORKS.TRON_SHASTA, payTo: PAY_TO_ADDRESS },
];
if (gasfreeEnabledShasta) {
  shastaPriceSchemes.push({ price: '0.0001 USDT', scheme: 'exact_gasfree', network: NETWORKS.TRON_SHASTA, payTo: PAY_TO_ADDRESS });
}
const shastaAccepts = await buildAccepts(shastaPriceSchemes);

app.get(
  '/protected-shasta',
  x402Hono({ facilitator, accepts: shastaAccepts }),
  async (c) => {
    const count = ++requestCount;
    console.log(`[Shasta] Serving protected image (req #${count})`);
    return new Response(getProtectedImageBytes(), {
      headers: { 'Content-Type': 'image/png' },
    });
  },
);

// TRON Mainnet
const mainnetPriceSchemes: Array<{ price: string; scheme: string; network: string; payTo: string }> = [
  { price: '0.0001 USDT', scheme: 'exact_permit', network: NETWORKS.TRON_MAINNET, payTo: PAY_TO_ADDRESS },
  { price: '0.0001 USDD', scheme: 'exact_permit', network: NETWORKS.TRON_MAINNET, payTo: PAY_TO_ADDRESS },
];
if (gasfreeEnabledMainnet) {
  mainnetPriceSchemes.push({ price: '0.0001 USDT', scheme: 'exact_gasfree', network: NETWORKS.TRON_MAINNET, payTo: PAY_TO_ADDRESS });
}
const mainnetAccepts = await buildAccepts(mainnetPriceSchemes);

app.get(
  '/protected-mainnet',
  x402Hono({ facilitator, accepts: mainnetAccepts }),
  async (c) => {
    const count = ++requestCount;
    console.log(`[Mainnet] Serving protected image (req #${count})`);
    return new Response(getProtectedImageBytes(), {
      headers: { 'Content-Type': 'image/png' },
    });
  },
);

// BSC (conditional on BSC_PAY_TO_ADDRESS)
if (BSC_PAY_TO_ADDRESS) {
  const bscTestAccepts = await buildAccepts([
    { price: '0.0001 USDT', scheme: 'exact_permit', network: NETWORKS.BSC_TESTNET, payTo: BSC_PAY_TO_ADDRESS },
    { price: '0.0001 USDC', scheme: 'exact_permit', network: NETWORKS.BSC_TESTNET, payTo: BSC_PAY_TO_ADDRESS },
    { price: '0.0001 DHLU', scheme: 'exact',        network: NETWORKS.BSC_TESTNET, payTo: BSC_PAY_TO_ADDRESS },
  ]);
  app.get(
    '/protected-bsc-testnet',
    x402Hono({ facilitator, accepts: bscTestAccepts }),
    async (c) => {
      const count = ++requestCount;
      console.log(`[BSC Testnet] Serving protected image (req #${count})`);
      return new Response(getProtectedImageBytes(), {
        headers: { 'Content-Type': 'image/png' },
      });
    },
  );

  const bscMainAccepts = await buildAccepts([
    { price: '0.0001 USDC', scheme: 'exact_permit', network: NETWORKS.BSC_MAINNET, payTo: BSC_PAY_TO_ADDRESS },
    { price: '0.0001 USDT', scheme: 'exact_permit', network: NETWORKS.BSC_MAINNET, payTo: BSC_PAY_TO_ADDRESS },
    { price: '0.0001 EPS',  scheme: 'exact_permit', network: NETWORKS.BSC_MAINNET, payTo: BSC_PAY_TO_ADDRESS },
  ]);
  app.get(
    '/protected-bsc-mainnet',
    x402Hono({ facilitator, accepts: bscMainAccepts }),
    async (c) => {
      const count = ++requestCount;
      console.log(`[BSC Mainnet] Serving protected image (req #${count})`);
      return new Response(getProtectedImageBytes(), {
        headers: { 'Content-Type': 'image/png' },
      });
    },
  );
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
console.log('\n' + '='.repeat(80));
console.log('Starting X402 Protected Resource Server (TypeScript)');
console.log('='.repeat(80));
console.log(`Host  : ${SERVER_HOST}`);
console.log(`Port  : ${SERVER_PORT}`);
console.log('Endpoints:');
console.log('  /protected-nile         — Nile testnet  (0.0001 USDT)');
console.log('  /protected-shasta       — Shasta testnet (0.0001 USDT)');
console.log('  /protected-mainnet      — TRON Mainnet  (0.0001 USDT/USDD)');
if (BSC_PAY_TO_ADDRESS) {
  console.log('  /protected-bsc-testnet  — BSC Testnet  (0.0001 USDT/USDC/DHLU)');
  console.log('  /protected-bsc-mainnet  — BSC Mainnet  (0.0001 USDC/USDT/EPS)');
}
console.log('='.repeat(80) + '\n');

serve({
  fetch: app.fetch,
  hostname: SERVER_HOST,
  port: SERVER_PORT,
});
