from typing import Dict, Any
from core.transaction import Transaction


class Node:
    def __init__(self, node_id: str):
        self.node_id = node_id
    
    def create_energy_transaction(
        self,
        amount_kwh: float,
        source_id: str,
        parent1: str,
        parent2: str
    ) -> Transaction:
        payload = {
            "type": "energy_contribution",
            "amount_kwh": amount_kwh,
            "source_id": source_id
        }
        return Transaction(payload, parent1, parent2, self.node_id)