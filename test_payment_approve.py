import os
from dotenv import load_dotenv
from tronpy import Tron
from tronpy.providers import HTTPProvider
from tronpy.keys import PrivateKey

load_dotenv(".env")
pk = PrivateKey(bytes.fromhex(os.getenv("TRON_CLIENT_PRIVATE_KEY").removeprefix("0x")))
client_addr = pk.public_key.to_base58check_address()

client = Tron(HTTPProvider("https://nile.trongrid.io"))
usdt = client.get_contract("TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf")
permit2 = "TYQuuhGbEMxF7nZxUHV3uHJxAVVAegNU9h"

print(f"Approving {permit2} to spend tokens from {client_addr}...")
txn = (
    usdt.functions.approve(permit2, 2**256 - 1)
    .with_owner(client_addr)
    .fee_limit(1_000_000_000)
    .build()
    .sign(pk)
)
result = txn.broadcast()
print("Approval TX:", result)
