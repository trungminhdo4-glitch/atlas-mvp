import time
from core.crypto import hash_data


class Transaction:
    """Basis-Transaction Klasse"""
    
    def __init__(self, payload, parent1, parent2, node_address, signature=None):
        self.payload = payload
        self.parent1 = parent1
        self.parent2 = parent2
        self.node_address = node_address
        self.timestamp = int(time.time())
        self.signature = signature
        self.hash = self._calculate_hash()
    
    def _calculate_hash(self):
        """Eindeutiger Hash basierend auf Inhalt"""
        data = {
            "payload": self.payload,
            "parent1": self.parent1,
            "parent2": self.parent2,
            "node": self.node_address,
            "timestamp": self.timestamp,
            "signature": self.signature
        }
        return hash_data(data)
    
    def to_dict(self):
        """Serialisierung"""
        return {
            "hash": self.hash,
            "payload": self.payload,
            "parent1": self.parent1,
            "parent2": self.parent2,
            "node": self.node_address,
            "timestamp": self.timestamp,
            "signature": self.signature
        }
    
    def get_transaction_type(self):
        """Gibt Transaktionstyp zurück"""
        return self.payload.get("type", "unknown")
    
    def is_energy_contribution(self):
        """Prüft ob Energie-Transaktion"""
        return self.get_transaction_type() == "energy_contribution"
    
    def get_energy_amount(self):
        """Gibt kWh zurück"""
        if self.is_energy_contribution():
            return self.payload.get("amount_kwh", 0)
        return 0


class EnergyTransaction(Transaction):
    """Spezialisierte Transaction für Energie-Meldungen"""
    
    def __init__(self, amount_kwh, source_id, node_address, parent1, parent2, signature=None):
        payload = {
            "type": "energy_contribution",
            "amount_kwh": float(amount_kwh),
            "source_id": source_id
        }
        super().__init__(
            payload=payload,
            parent1=parent1,
            parent2=parent2,
            node_address=node_address,
            signature=signature
        )