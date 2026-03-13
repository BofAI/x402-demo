import os
from dotenv import load_dotenv
import httpx

from bankofai.x402 import x402ClientSync
from bankofai.x402.mechanisms.tron import ClientTronSigner, register_exact_tron_client
from bankofai.x402.http import x402HTTPClientSync

load_dotenv(".env")
client = x402ClientSync()
tron_signer = ClientTronSigner(private_key=os.getenv("TRON_CLIENT_PRIVATE_KEY"))
register_exact_tron_client(client, tron_signer)

with httpx.Client(timeout=120.0) as http:
    payment_client = x402HTTPClientSync(client)
    url = "http://localhost:8010/protected-nile"
    res1 = http.get(url)
    
    print("Initial GET response STATUS:", res1.status_code)
    print("Initial GET response HEADERS:", dict(res1.headers))
    
    if res1.status_code == 402:
        print("Received 402. Preparing payment...")
        req = payment_client.get_payment_required_response(lambda h: res1.headers.get(h), res1.content)
        print("PARSED REQUIREMENT:", req.model_dump_json(indent=2) if req else None)
        payload = client.create_payment_payload(req)
        headers = payment_client.encode_payment_signature_header(payload)
        res2 = http.get(url, headers=headers)
        print("Final Status:", res2.status_code)
        print("Final Headers:", dict(res2.headers))
        print("Response Body:", res2.text)
