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
  AgentWalletAdapter,
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

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, '../../../.env') });

const TRON_PRIVATE_KEY = process.env.TRON_PRIVATE_KEY ?? '';
const BSC_PRIVATE_KEY  = process.env.BSC_PRIVATE_KEY ?? '';
const SIGNER_INIT_MODE = (process.env.SIGNER_INIT_MODE ?? 'private_key').trim().toLowerCase();

const TRON_AGENT_WALLET_NAME = process.env.TRON_AGENT_WALLET_NAME ?? '';
const BSC_AGENT_WALLET_NAME = process.env.BSC_AGENT_WALLET_NAME ?? '';
const AGENT_WALLET_SECRETS_DIR = process.env.AGENT_WALLET_SECRETS_DIR ?? '~/.agent-wallet';
const AGENT_WALLET_PASSWORD = process.env.AGENT_WALLET_PASSWORD ?? '';

const SERVER_URL       = process.env.SERVER_URL ?? 'http://localhost:8000';
// For TRON mainnet, set TRON_GRID_API_KEY in .env — the signer reads it from env automatically.

// Change ENDPOINT to target a different server resource.
// The server may return accepts[] spanning multiple networks.
const ENDPOINT         = '/protected-nile';
// const ENDPOINT         = '/protected-mainnet';
// const ENDPOINT         = '/protected-bsc-mainnet';
// const ENDPOINT         = '/protected-bsc-testnet';

if (!['private_key', 'agent_wallet'].includes(SIGNER_INIT_MODE)) {
  console.error('Error: SIGNER_INIT_MODE must be one of: private_key, agent_wallet');
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
  // --- Create signers for every chain family ---
  let tronSigner: TronClientSigner;
  let evmSigner: EvmClientSigner | undefined;

  if (SIGNER_INIT_MODE === 'private_key') {
    if (!TRON_PRIVATE_KEY) {
      console.error('Error: TRON_PRIVATE_KEY not set in .env');
      process.exit(1);
    }

    tronSigner = TronClientSigner.fromPrivateKey(TRON_PRIVATE_KEY);
    if (BSC_PRIVATE_KEY) {
      evmSigner = EvmClientSigner.fromPrivateKey(BSC_PRIVATE_KEY);
    }
  } else {
    if (!TRON_AGENT_WALLET_NAME) {
      throw new Error('TRON_AGENT_WALLET_NAME is required for SIGNER_INIT_MODE=agent_wallet');
    }
    if (!AGENT_WALLET_PASSWORD) {
      throw new Error('AGENT_WALLET_PASSWORD is required for SIGNER_INIT_MODE=agent_wallet');
    }

    let WalletFactory: any;
    try {
      ({ WalletFactory } = await import('@bankofai/agent-wallet'));
    } catch {
      throw new Error('SIGNER_INIT_MODE=agent_wallet requires `@bankofai/agent-wallet` package in this client environment');
    }

    const provider = WalletFactory({
      secretsDir: AGENT_WALLET_SECRETS_DIR,
      password: AGENT_WALLET_PASSWORD,
    });
    const tronAgentWallet = await provider.getWallet(TRON_AGENT_WALLET_NAME);
    const tronWallet = await AgentWalletAdapter.create(tronAgentWallet);
    tronSigner = TronClientSigner.fromWallet(tronWallet);
    if (BSC_AGENT_WALLET_NAME) {
      const evmAgentWallet = await provider.getWallet(BSC_AGENT_WALLET_NAME);
      const evmWallet = await AgentWalletAdapter.create(evmAgentWallet);
      evmSigner = EvmClientSigner.fromWallet(evmWallet);
    }
  }

  hr();
  console.log('X402 Client (TypeScript · Multi-Network)');
  hr();
  console.log(`  TRON Address : ${tronSigner.getAddress()}`);
  console.log(`  Init Mode    : ${SIGNER_INIT_MODE}`);
  if (evmSigner) {
    console.log(`  EVM  Address : ${evmSigner.getAddress()}`);
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

  if (evmSigner) {
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
