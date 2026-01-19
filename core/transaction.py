import time
import hashlib
import json
from typing import Any, Dict, Optional


class Transaction:
    def __init__(
        self,
        payload: Dict[str, Any],
        parent1: str,
        parent2: str,
        node_id: str,
        signature: Optional[str] = None
    ):
        self.payload = payload
        self.parent1 = parent1
        self.parent2 = parent2
        self.node_id = node_id
        self.timestamp = int(time.time())
        self.signature = signature
        self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        data = {
            "payload": self.payload,
            "parent1": self.parent1,
            "parent2": self.parent2,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "signature": self.signature
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash": self.hash,
            "payload": self.payload,
            "parent1": self.parent1,
            "parent2": self.parent2,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "signature": self.signature
        }
    
    def is_energy_contribution(self) -> bool:
        return self.payload.get("type") == "energy_contribution"
    
    def get_energy_kwh(self) -> float:
        if self.is_energy_contribution():
            return float(self.payload.get("amount_kwh", 0.0))
        return 0.0