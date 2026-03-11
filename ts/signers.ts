/**
 * TronWeb-based signer adapters for x402 TRON mechanisms.
 *
 * Wraps TronWeb 6.x into the ClientTronSigner and FacilitatorTronSigner
 * interfaces expected by @bankofai/x402-tron.
 */

import type { ClientTronSigner, FacilitatorTronSigner } from "@bankofai/x402-tron";
import { recoverTypedDataAddress, type Hex } from "viem";

// TronWeb types (simplified — TronWeb 6.x doesn't ship great TS types)
type TronWebInstance = any;

// ---------------------------------------------------------------------------
// Client signer
// ---------------------------------------------------------------------------

export function createClientTronSigner(
  tronWeb: TronWebInstance,
  privateKey: string,
): ClientTronSigner {
  const addr: string = tronWeb.defaultAddress?.base58 ?? tronWeb.address.fromPrivateKey(privateKey);

  return {
    address: addr,

    async signTypedData(args) {
      // TronWeb 6.x: trx._signTypedData(domain, types, value, privateKey)
      const cleanKey = privateKey.replace(/^0x/, "");
      const sig = await tronWeb.trx._signTypedData(
        args.domain,
        args.types,
        args.message,
        cleanKey,
      );
      return sig as `0x${string}`;
    },

    async readContract(args) {
      const contract = await tronWeb.contract(args.abi as any[], args.address);
      const method = contract.methods[args.functionName];
      if (!method) throw new Error(`Method ${args.functionName} not found on contract ${args.address}`);
      return method(...args.args).call();
    },
  };
}

// ---------------------------------------------------------------------------
// Facilitator signer
// ---------------------------------------------------------------------------

export function createFacilitatorTronSigner(
  tronWeb: TronWebInstance,
  privateKey: string,
): FacilitatorTronSigner {
  const addr: string = tronWeb.defaultAddress?.base58 ?? tronWeb.address.fromPrivateKey(privateKey);

  return {
    getAddresses() {
      return [addr] as const;
    },

    async readContract(args) {
      const contract = await tronWeb.contract(args.abi as any[], args.address);
      const method = contract.methods[args.functionName];
      if (!method) throw new Error(`Method ${args.functionName} not found on contract ${args.address}`);
      return method(...args.args).call();
    },

    async verifyTypedData(args) {
      // Use viem's recoverTypedDataAddress to recover signer, then compare
      try {
        const recovered = await recoverTypedDataAddress({
          domain: args.domain as any,
          types: args.types as any,
          primaryType: args.primaryType,
          message: args.message as any,
          signature: args.signature as Hex,
        });

        // Normalize both to lowercase hex for comparison
        const expectedHex = tronWeb.address.toHex(args.address).toLowerCase().replace(/^41/, "0x");
        const recoveredHex = recovered.toLowerCase();
        return expectedHex === recoveredHex;
      } catch (e) {
        console.error("[verifyTypedData] Recovery failed:", e);
        return false;
      }
    },

    async writeContract(args) {
      const contract = await tronWeb.contract(args.abi as any[], args.address);
      const method = contract.methods[args.functionName];
      if (!method) throw new Error(`Method ${args.functionName} not found on contract ${args.address}`);
      const txId = await method(...args.args).send({
        feeLimit: 150_000_000, // 150 TRX max fee
      });
      return typeof txId === "string" ? txId : txId.txid ?? txId;
    },

    async waitForTransactionReceipt(args) {
      // Poll for transaction info until confirmed
      const maxAttempts = 30;
      const interval = 3000;
      for (let i = 0; i < maxAttempts; i++) {
        try {
          const info = await tronWeb.trx.getTransactionInfo(args.hash);
          if (info && info.id) {
            const status = info.receipt?.result === "SUCCESS" ? "success" : "reverted";
            return { status };
          }
        } catch {
          // Not confirmed yet
        }
        await new Promise((r) => setTimeout(r, interval));
      }
      throw new Error(`Transaction ${args.hash} not confirmed after ${maxAttempts * interval / 1000}s`);
    },
  };
}
