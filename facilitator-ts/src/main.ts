/**
 * X402 Demo — TypeScript Payment Facilitator (Hono)
 *
 * TypeScript port of `facilitator/main.py`. Exposes the standard x402
 * facilitator HTTP API:
 *
 *   GET  /supported    — list (network, scheme) pairs this facilitator handles
 *   POST /fee/quote    — quote the facilitator fee for a set of requirements
 *   POST /verify       — off-chain signature / timing / replay checks
 *   POST /settle       — on-chain settlement
 *
 * Uses:
 *   - X402Facilitator                     (core engine)
 *   - ExactPermitTronFacilitatorMechanism (TRON permit scheme)
 *   - ExactGasFreeFacilitatorMechanism    (TRON gasfree scheme)
 *   - ExactPermitEvmFacilitatorMechanism  (BSC permit scheme)
 *   - ExactEvmFacilitatorMechanism        (BSC exact scheme)
 *   - TronClientSigner / EvmClientSigner  (wallet signers)
 *   - Hono                                (HTTP framework)
 *
 * Run:
 *   FACILITATOR_PORT=8001 tsx src/main.ts
 */

import { serve } from '@hono/node-server';
import { config } from 'dotenv';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

import {
  X402Facilitator,
  ExactPermitTronFacilitatorMechanism,
  ExactGasFreeFacilitatorMechanism,
  ExactPermitEvmFacilitatorMechanism,
  ExactEvmFacilitatorMechanism,
  TronFacilitatorSigner,
  EvmFacilitatorSigner,
  GasFreeAPIClient,
  getGasFreeApiBaseUrl,
  getNetworkTokens,
  getPaymentPermitAddress,
  NETWORKS,
} from '@bankofai/x402';

// ---------------------------------------------------------------------------
// Env
// ---------------------------------------------------------------------------
const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, '../../.env') });

const FACILITATOR_HOST = process.env.FACILITATOR_HOST ?? '0.0.0.0';
const FACILITATOR_PORT = parseInt(process.env.FACILITATOR_PORT ?? '8001', 10);

// GasFree enable flags (default: true; set to "false" to disable)
const gasfreeEnabledNile    = (process.env.GASFREE_ENABLED_NILE    ?? 'true') !== 'false';
const gasfreeEnabledShasta  = (process.env.GASFREE_ENABLED_SHASTA  ?? 'true') !== 'false';
const gasfreeEnabledMainnet = (process.env.GASFREE_ENABLED_MAINNET ?? 'true') !== 'false';

// TRON networks handled
const TRON_NETWORKS = ['mainnet', 'shasta', 'nile'] as const;

// Base fee per token (smallest unit) — mirrors Python facilitator/main.py
const TRON_BASE_FEE: Record<string, string> = {
  USDT: '100',           // 0.0001 USDT (6 decimals)
  USDD: '100000000000000', // 0.0001 USDD (18 decimals)
};
const BSC_BASE_FEE: Record<string, string> = {
  USDT: '100000000000000', // 0.0001 USDT (18 decimals on BSC)
  USDC: '100000000000000', // 0.0001 USDC (18 decimals on BSC)
};
const BSC_MAINNET_BASE_FEE: Record<string, string> = {
  EPS: '100000000000000', // 0.0001 EPS (18 decimals on BSC mainnet)
};

// Helper: get GasFree API base URL (env override → config fallback)
function resolveGasFreeBaseUrl(network: string): string {
  const envSuffix = network.split(':').at(-1)?.toUpperCase();
  return process.env[`GASFREE_API_BASE_URL_${envSuffix}`] ?? getGasFreeApiBaseUrl(network);
}

// ---------------------------------------------------------------------------
// Bootstrap — async init (signers require async wallet resolution)
// ---------------------------------------------------------------------------
async function createFacilitator(): Promise<X402Facilitator> {
  const facilitator = new X402Facilitator();

  // --- TRON facilitator signer ---
  const tronSigner = await TronFacilitatorSigner.create();
  const tronAddress = tronSigner.getAddress();
  console.log(`TRON Facilitator Address: ${tronAddress}`);

  // GasFree API clients (per enabled network)
  const gasfreeClients: Record<string, GasFreeAPIClient> = {};
  const gasfreeFlags: Record<string, boolean> = {
    nile:    gasfreeEnabledNile,
    shasta:  gasfreeEnabledShasta,
    mainnet: gasfreeEnabledMainnet,
  };
  for (const [suffix, enabled] of Object.entries(gasfreeFlags)) {
    if (enabled) {
      const netKey = `tron:${suffix}`;
      gasfreeClients[netKey] = new GasFreeAPIClient(resolveGasFreeBaseUrl(netKey));
    }
  }

  // Register TRON mechanisms — new signature uses symbol-keyed base fee map.
  for (const suffix of TRON_NETWORKS) {
    const netKey = `tron:${suffix}`;

    // exact_permit
    facilitator.register(
      [netKey],
      new ExactPermitTronFacilitatorMechanism(tronSigner, {
        feeTo: tronAddress,
        baseFee: TRON_BASE_FEE,
      }),
    );

    // exact_gasfree (conditional)
    if (gasfreeFlags[suffix] && gasfreeClients[netKey]) {
      facilitator.register(
        [netKey],
        new ExactGasFreeFacilitatorMechanism(tronSigner, {
          feeTo: tronAddress,
          clients: gasfreeClients,
          baseFee: TRON_BASE_FEE,
        }),
      );
    }
  }

  // --- EVM / BSC facilitator signer ---
  const evmSigner = await EvmFacilitatorSigner.create();
  const evmAddress = evmSigner.getAddress();
  console.log(`EVM  Facilitator Address: ${evmAddress}`);

  // BSC Testnet
  facilitator.register(
    [NETWORKS.BSC_TESTNET],
    new ExactPermitEvmFacilitatorMechanism(evmSigner, {
      feeTo: evmAddress,
      baseFee: BSC_BASE_FEE,
    }),
  );
  facilitator.register([NETWORKS.BSC_TESTNET], new ExactEvmFacilitatorMechanism(evmSigner));

  // BSC Mainnet
  facilitator.register(
    [NETWORKS.BSC_MAINNET],
    new ExactPermitEvmFacilitatorMechanism(evmSigner, {
      feeTo: evmAddress,
      baseFee: { ...BSC_BASE_FEE, ...BSC_MAINNET_BASE_FEE },
    }),
  );
  facilitator.register([NETWORKS.BSC_MAINNET], new ExactEvmFacilitatorMechanism(evmSigner));

  return facilitator;
}

// ---------------------------------------------------------------------------
// Hono app
// ---------------------------------------------------------------------------
function buildApp(facilitator: X402Facilitator): Hono {
  const app = new Hono();

  app.use('*', cors({ origin: '*', exposeHeaders: ['*'] }));

  // GET /supported
  app.get('/supported', (c) => c.json(facilitator.supported()));

  // POST /fee/quote
  app.post('/fee/quote', async (c) => {
    try {
      const body = await c.req.json<{ accepts: unknown[]; paymentPermitContext?: Record<string, unknown> }>();
      const result = await facilitator.feeQuote(body.accepts as any, body.paymentPermitContext);
      return c.json(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return c.json({ error: msg }, 400);
    }
  });

  // POST /verify
  app.post('/verify', async (c) => {
    try {
      const body = await c.req.json<{ paymentPayload: unknown; paymentRequirements: unknown }>();
      console.log('[VERIFY]', JSON.stringify(body.paymentPayload));
      const result = await facilitator.verify(body.paymentPayload as any, body.paymentRequirements as any);
      console.log('[VERIFY result]', JSON.stringify(result));
      return c.json(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('[VERIFY error]', msg);
      return c.json({ error: msg }, 500);
    }
  });

  // POST /settle
  app.post('/settle', async (c) => {
    try {
      const body = await c.req.json<{ paymentPayload: unknown; paymentRequirements: unknown }>();
      const result = await facilitator.settle(body.paymentPayload as any, body.paymentRequirements as any);
      return c.json(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('[SETTLE error]', msg);
      return c.json({ error: msg }, 500);
    }
  });

  return app;
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------
async function main(): Promise<void> {
  console.log('='.repeat(80));
  console.log('X402 Payment Facilitator (TypeScript/Hono) — Starting');
  console.log('='.repeat(80));

  const facilitator = await createFacilitator();
  const app = buildApp(facilitator);

  const allNetworks = [
    ...TRON_NETWORKS.map((s) => `tron:${s}`),
    NETWORKS.BSC_TESTNET,
    NETWORKS.BSC_MAINNET,
  ];

  console.log('\nConfiguration:');
  console.log(`GasFree Nile   : ${gasfreeEnabledNile}`);
  console.log(`GasFree Shasta : ${gasfreeEnabledShasta}`);
  console.log(`GasFree Mainnet: ${gasfreeEnabledMainnet}`);
  console.log(`TRON Base Fee  : ${JSON.stringify(TRON_BASE_FEE)}`);
  console.log(`BSC  Base Fee  : ${JSON.stringify(BSC_BASE_FEE)}`);

  console.log('\nNetwork Details:');
  for (const net of allNetworks) {
    console.log(`  ${net}:`);
    console.log(`    PaymentPermit: ${getPaymentPermitAddress(net)}`);
    const tokens = getNetworkTokens(net);
    for (const [sym, info] of Object.entries(tokens)) {
      console.log(`    ${sym}: ${info.address} (decimals=${info.decimals})`);
    }
  }

  console.log('\n' + '='.repeat(80));
  console.log('Starting X402 Facilitator');
  console.log('='.repeat(80));
  console.log(`Host : ${FACILITATOR_HOST}`);
  console.log(`Port : ${FACILITATOR_PORT}`);
  console.log('\nEndpoints:');
  console.log(`  GET  http://${FACILITATOR_HOST}:${FACILITATOR_PORT}/supported`);
  console.log(`  POST http://${FACILITATOR_HOST}:${FACILITATOR_PORT}/fee/quote`);
  console.log(`  POST http://${FACILITATOR_HOST}:${FACILITATOR_PORT}/verify`);
  console.log(`  POST http://${FACILITATOR_HOST}:${FACILITATOR_PORT}/settle`);
  console.log('='.repeat(80) + '\n');

  serve({
    fetch: app.fetch,
    hostname: FACILITATOR_HOST,
    port: FACILITATOR_PORT,
  });
}

main().catch((err) => {
  console.error('❌ Fatal:', err instanceof Error ? err.message : err);
  process.exit(1);
});
