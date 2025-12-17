import base64
import time
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def load_private_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign_key(private_key, message: str) -> str:
    sig = private_key.sign(
        message.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode()


class KalshiClient:
    def __init__(self, api_key_id: str, private_key_path: str, env: str = "demo"):
        self.api_key_id = api_key_id
        self.private_key = load_private_key(private_key_path)
        self.base_url = (
            "https://demo-api.kalshi.co"
            if env == "demo"
            else "https://api.elections.kalshi.com"
        )

    def headers(self, method: str, url: str) -> dict:
        ts = str(int(time.time() * 1000))
        path = urlparse(url).path
        msg = f"{ts}{method}{path}"

        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sign_key(self.private_key, msg),
        }

    def get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        headers = self.headers("GET", url)
        print(url)
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
