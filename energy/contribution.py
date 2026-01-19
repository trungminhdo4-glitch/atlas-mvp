from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class EnergyContribution:
    node_id: str
    amount_kwh: float
    source_id: str
    transaction_hash: str
    
    @classmethod
    def from_transaction(cls, tx_hash: str, tx_dict: Dict[str, Any]) -> "EnergyContribution":
        payload = tx_dict["payload"]
        return cls(
            node_id=tx_dict["node_id"],
            amount_kwh=float(payload["amount_kwh"]),
            source_id=str(payload["source_id"]),
            transaction_hash=tx_hash
        )