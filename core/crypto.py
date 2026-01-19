import hashlib
import json
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


class Wallet:
    """Verwaltet Private/Public Key Pair"""
    
    def __init__(self):
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.address = self._generate_address()
    
    def _generate_address(self):
        """Erstellt eindeutige Adresse aus Public Key"""
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return hashlib.sha256(pub_bytes).hexdigest()[:16]
    
    def get_address(self):
        """Gibt Wallet-Adresse zurück"""
        return self.address
    
    def sign(self, data):
        """Signiert Daten mit Private Key"""
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True)
        if isinstance(data, str):
            data = data.encode()
        return self.private_key.sign(data).hex()


def hash_data(data):
    """SHA-256 Hash einer Daten-Struktur"""
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()