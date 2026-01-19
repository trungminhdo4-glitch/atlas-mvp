from typing import Dict, List
from copy import deepcopy


class TokenLedger:
    def __init__(self):
        self.balances: Dict[str, float] = {}
        self.total_supply: float = 0.0
    
    def get_balance(self, node_id: str) -> float:
        return self.balances.get(node_id, 0.0)
    
    def credit_tokens(self, node_id: str, amount: float) -> None:
        if amount <= 0:
            return
        current = self.balances.get(node_id, 0.0)
        self.balances[node_id] = current + amount
        self.total_supply += amount
    
    def debit_tokens(self, node_id: str, amount: float) -> bool:
        if amount <= 0:
            return False
        current = self.balances.get(node_id, 0.0)
        if current < amount:
            return False
        self.balances[node_id] = current - amount
        return True
    
    def get_all_balances(self) -> Dict[str, float]:
        return deepcopy(self.balances)