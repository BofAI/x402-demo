/**
 * TronWeb-based signer adapters for x402 TRON mechanisms.
 *
 * Wraps TronWeb 6.x into the ClientTronSigner and FacilitatorTronSigner
 * interfaces expected by @bankofai/x402-tvm.
 */

import type { ClientTronSigner, FacilitatorTronSigner } from "@bankofai/x402-tvm";
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
        const normalize = (a: any) => {
          if (typeof a !== "string") return a;
          if (a.startsWith("T") && a.length === 34) {
            return tronWeb.address.toHex(a).toLowerCase().replace(/^41/, "0x") as Hex;
          }
          if (a.startsWith("0x")) return a.toLowerCase() as Hex;
          return a;
        };

        const domain = { ...args.domain } as any;
        if (domain.verifyingContract) domain.verifyingContract = normalize(domain.verifyingContract);

        const message = { ...args.message } as any;
        if (message.from) message.from = normalize(message.from);
        if (message.to) message.to = normalize(message.to);
        if (message.owner) message.owner = normalize(message.owner);
        if (message.spender) message.spender = normalize(message.spender);

        const recovered = await recoverTypedDataAddress({
          domain: domain,
          types: args.types as any,
          primaryType: args.primaryType,
          message: message,
          signature: args.signature as Hex,
        });

        const expectedHex = normalize(args.address);
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
