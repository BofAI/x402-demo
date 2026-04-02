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
import { createWalletClient, http, type Hex } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { bsc, bscTestnet } from 'viem/chains';
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

type AgentWallet = {
  getAddress(): Promise<string>;
  signMessage(msg: Uint8Array): Promise<string>;
  signTypedData(data: Record<string, unknown>): Promise<string>;
  signTransaction(payload: Record<string, unknown>): Promise<string>;
};

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, '../../../.env') });

const SERVER_URL       = process.env.SERVER_URL ?? 'http://localhost:8000';
const ENDPOINT         = process.env.ENDPOINT ?? '/protected-nile';
const PREFERRED_NETWORK = process.env.PREFERRED_NETWORK;
const BSC_CLIENT_PRIVATE_KEY = process.env.BSC_CLIENT_PRIVATE_KEY;
const BSC_TESTNET_RPC_URL = process.env.BSC_TESTNET_RPC_URL ?? 'https://data-seed-prebsc-1-s1.binance.org:8545';

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

function createLocalEvmWallet(privateKey: Hex): AgentWallet {
  const account = privateKeyToAccount(privateKey);

  return {
    async getAddress(): Promise<string> {
      return account.address;
    },
    async signMessage(msg: Uint8Array): Promise<string> {
      return account.signMessage({ message: { raw: msg } });
    },
    async signTypedData(data: Record<string, unknown>): Promise<string> {
      const {
        domain,
        types,
        primaryType,
        message,
      } = data as {
        domain: Record<string, unknown>;
        types: Record<string, unknown>;
        primaryType: string;
        message: Record<string, unknown>;
      };
      const normalizedTypes = { ...types } as Record<string, unknown>;
      delete normalizedTypes.EIP712Domain;
      return account.signTypedData({
        domain: domain as any,
        types: normalizedTypes as any,
        primaryType: primaryType as any,
        message: message as any,
      });
    },
    async signTransaction(payload: Record<string, unknown>): Promise<string> {
      const chainId = Number(payload.chainId ?? 97);
      const chain = chainId === 56 ? bsc : bscTestnet;
      const rpcUrl = chainId === 56
        ? (process.env.BSC_MAINNET_RPC_URL ?? 'https://bsc-dataseed.binance.org')
        : BSC_TESTNET_RPC_URL;
      const client = createWalletClient({
        account,
        chain,
        transport: http(rpcUrl),
      });
      const signed = await client.signTransaction(payload as any);
      return signed.replace(/^0x/, '');
    },
  };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  // --- Create signers for every chain family ---
  let tronSigner: TronClientSigner | null = null;
  try {
    tronSigner = await TronClientSigner.create();
  } catch (error) {
    if (!PREFERRED_NETWORK?.startsWith('tron:')) {
      console.warn('Skipping TRON signer:', error instanceof Error ? error.message : String(error));
    } else {
      throw error;
    }
  }

  const localEvmWallet = BSC_CLIENT_PRIVATE_KEY
    ? createLocalEvmWallet(BSC_CLIENT_PRIVATE_KEY as Hex)
    : null;
  const evmSigner = localEvmWallet
    ? new EvmClientSigner(localEvmWallet)
    : await EvmClientSigner.create();
  if (BSC_CLIENT_PRIVATE_KEY) {
    evmSigner.setAddress(await localEvmWallet!.getAddress());
  }

  hr();
  console.log('X402 Client (TypeScript · Multi-Network)');
  hr();
  if (tronSigner) console.log(`  TRON Address : ${tronSigner.getAddress()}`);
  console.log(`  BSC Address  : ${evmSigner.getAddress()}`);
  if (PREFERRED_NETWORK) console.log(`  Preferred    : ${PREFERRED_NETWORK}`);
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
  if (tronSigner) {
    x402.register('tron:*', new ExactPermitTronClientMechanism(tronSigner));
    x402.register('tron:*', new ExactGasFreeClientMechanism(tronSigner, gasfreeClients));
  }

  x402.register('eip155:97', new ExactPermitEvmClientMechanism(evmSigner));
  x402.register('eip155:97', new ExactEvmClientMechanism(evmSigner));
  x402.register('eip155:56', new ExactPermitEvmClientMechanism(evmSigner));
  x402.register('eip155:56', new ExactEvmClientMechanism(evmSigner));

  // Balance policy: auto-resolves signers from registered mechanisms
  x402.registerPolicy(SufficientBalancePolicy);

  if (PREFERRED_NETWORK) {
    const preferredNetwork = PREFERRED_NETWORK;
    x402.registerPolicy({
      apply(requirements: PaymentRequirements[]): PaymentRequirements[] {
        const preferred = requirements.filter((req) => req.network === preferredNetwork);
        return preferred.length > 0 ? preferred : requirements;
      },
    });
  }

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
