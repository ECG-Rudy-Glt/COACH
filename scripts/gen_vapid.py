"""Génère une paire de clés VAPID (Web Push) : affiche « privée publique » en base64 url-safe, sans remplissage."""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
key = ec.generate_private_key(ec.SECP256R1())
priv = b64(key.private_numbers().private_value.to_bytes(32, "big"))
pub = b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
print(priv, pub)
