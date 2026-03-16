/**
 * X402 Demo - TypeScript Client (Multi-Network)
 *
 * Registers BOTH TRON and EVM mechanisms by default so the client can
 * handle 402 responses from any supported chain.  The server decides
 * which network(s) to accept; the SDK picks the best affordable option.
 */

import { config } from 'dotenv';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import { writeFileSync } from 'fs';
import { tmpdir } from 'os';
import {
  X402Client,
  X402FetchClient,
  ExactPermitTronClientMechanism,
  ExactGasFreeClientMechanism,
  ExactPermitEvmClientMechanism,
  ExactEvmClientMechanism,
  TronClientSigner,
  EvmClientSigner,
  DefaultTokenSelectionStrategy,
  SufficientBalancePolicy,
  decodePaymentPayload,
  type SettleResponse,
  type PaymentPolicy,
  type PaymentRequirements,
  GasFreeAPIClient,
  getGasFreeApiBaseUrl,
  findByAddress,
} from '@bankofai/x402';
import { TronWallet, EvmWallet } from '@bankofai/agent-wallet';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, '../../../.env') });

const TRON_PRIVATE_KEY = process.env.TRON_PRIVATE_KEY ?? '';
const BSC_PRIVATE_KEY  = process.env.BSC_PRIVATE_KEY ?? '';
const SERVER_URL       = process.env.SERVER_URL ?? 'http://localhost:8000';
// For TRON mainnet, set TRON_GRID_API_KEY in .env — the signer reads it from env automatically.

// Change ENDPOINT to target a different server resource.
// The server may return accepts[] spanning multiple networks.
const ENDPOINT         = '/protected-nile';
// const ENDPOINT         = '/protected-mainnet';
// const ENDPOINT         = '/protected-bsc-mainnet';
// const ENDPOINT         = '/protected-bsc-testnet';


if (!TRON_PRIVATE_KEY) {
  console.error('Error: TRON_PRIVATE_KEY not set in .env');
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const hr = () => console.log('─'.repeat(72));

function printSettlement(header: string): void {
  const settle = decodePaymentPayload<SettleResponse>(header);
  console.log('Settlement:');
  console.log(`  success : ${settle.success}`);
  console.log(`  network : ${settle.network}`);
  console.log(`  tx      : ${settle.transaction}`);
  if (settle.errorReason) console.log(`  error   : ${settle.errorReason}`);
}

async function saveImage(response: Response): Promise<string> {
  const ct = response.headers.get('content-type') ?? '';
  const ext = ct.includes('jpeg') || ct.includes('jpg') ? 'jpg'
            : ct.includes('webp') ? 'webp' : 'png';
  const buf = Buffer.from(await response.arrayBuffer());
  const path = join(tmpdir(), `x402_${Date.now()}.${ext}`);
  writeFileSync(path, buf);
  return path;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  // --- Create wallets from agent-wallet ---
  const cleanTronKey = TRON_PRIVATE_KEY.startsWith('0x') ? TRON_PRIVATE_KEY.slice(2) : TRON_PRIVATE_KEY;
  const tronWallet = new TronWallet(Buffer.from(cleanTronKey, 'hex'));

  // --- Create signers for every chain family ---
  const tronSigner = await TronClientSigner.create(tronWallet);

  hr();
  console.log('X402 Client (TypeScript · Multi-Network)');
  hr();
  console.log(`  TRON Address : ${tronSigner.getAddress()}`);
  if (BSC_PRIVATE_KEY) {
    const cleanBscKey = BSC_PRIVATE_KEY.startsWith('0x') ? BSC_PRIVATE_KEY.slice(2) : BSC_PRIVATE_KEY;
    const evmWalletPreview = new EvmWallet(Buffer.from(cleanBscKey, 'hex'));
    const evmSignerPreview = await EvmClientSigner.create(evmWalletPreview);
    console.log(`  EVM  Address : ${evmSignerPreview.getAddress()}`);
  } else {
    console.log('  EVM: not configured (BSC_PRIVATE_KEY not set)');
  }
  console.log(`  Resource     : ${SERVER_URL}${ENDPOINT}`);
  hr();

  // --- Initialize GasFree API clients ---
  const gasfreeClients: Record<string, GasFreeAPIClient> = {
    'tron:nile': new GasFreeAPIClient(getGasFreeApiBaseUrl('tron:nile')),
    'tron:shasta': new GasFreeAPIClient(getGasFreeApiBaseUrl('tron:shasta')),
    'tron:mainnet': new GasFreeAPIClient(getGasFreeApiBaseUrl('tron:mainnet')),
  };

  // --- Register mechanisms for ALL networks ---
  const x402 = new X402Client({ tokenStrategy: new DefaultTokenSelectionStrategy() });
  x402.register('tron:*', new ExactPermitTronClientMechanism(tronSigner));
  x402.register('tron:*', new ExactGasFreeClientMechanism(tronSigner, gasfreeClients));

  if (BSC_PRIVATE_KEY) {
    const cleanBscKey = BSC_PRIVATE_KEY.startsWith('0x') ? BSC_PRIVATE_KEY.slice(2) : BSC_PRIVATE_KEY;
    const evmWallet = new EvmWallet(Buffer.from(cleanBscKey, 'hex'));
    const evmSigner = await EvmClientSigner.create(evmWallet);
    x402.register('eip155:97', new ExactPermitEvmClientMechanism(evmSigner));
    x402.register('eip155:97', new ExactEvmClientMechanism(evmSigner));
    x402.register('eip155:56', new ExactPermitEvmClientMechanism(evmSigner));
    x402.register('eip155:56', new ExactEvmClientMechanism(evmSigner));
  }

  // Balance policy: auto-resolves signers from registered mechanisms
  x402.registerPolicy(SufficientBalancePolicy);

  // Prefer exact_gasfree USDT (same as Python client's PreferGasFreeUSDTPolicy)
  x402.registerPolicy({
    apply(requirements: PaymentRequirements[]): PaymentRequirements[] {
      for (const req of requirements) {
        const tokenInfo = findByAddress(req.network, req.asset);
        if (req.scheme === 'exact_gasfree' && tokenInfo?.symbol === 'USDT') {
          console.log(`🎯 Policy: Force selecting ${req.scheme} (${tokenInfo.symbol})`);
          return [req];
        }
      }
      return requirements;
    },
  });

  const client = new X402FetchClient(x402);

  const url = `${SERVER_URL}${ENDPOINT}`;
  console.log(`\nGET ${url} …`);

  const res = await client.get(url);
  console.log(`\n✅ ${res.status} ${res.statusText}`);

  const paymentHeader = res.headers.get('payment-response');
  if (paymentHeader) printSettlement(paymentHeader);

  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) {
    console.log(`\n${JSON.stringify(await res.json(), null, 2)}`);
  } else if (ct.includes('image/')) {
    const path = await saveImage(res);
    console.log(`\nImage saved → ${path}`);
  } else {
    const text = await res.text();
    console.log(`\n${text.slice(0, 500)}`);
  }
}

main().catch((err) => {
  console.error('\n❌', err instanceof Error ? err.message : err);
  process.exit(1);
});
