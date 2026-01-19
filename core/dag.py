from collections import defaultdict
from typing import Dict, List, Set, Tuple
from core.transaction import Transaction
import random


class DAG:
    GENESIS_HASH = "0" * 64
    
    def __init__(self):
        self.transactions: Dict[str, Transaction] = {}
        self.tips: Set[str] = {self.GENESIS_HASH}
        self.children: Dict[str, List[str]] = defaultdict(list)
        self.parents: Dict[str, Tuple[str, str]] = {}
        self.confirmations: Dict[str, int] = defaultdict(int)
    
    def add_transaction(self, tx: Transaction) -> bool:
        if tx.hash in self.transactions:
            return False
        
        if tx.parent1 != self.GENESIS_HASH and tx.parent1 not in self.transactions:
            return False
        if tx.parent2 != self.GENESIS_HASH and tx.parent2 not in self.transactions:
            return False
        
        self.transactions[tx.hash] = tx
        self.parents[tx.hash] = (tx.parent1, tx.parent2)
        
        if tx.parent1 != self.GENESIS_HASH:
            self.children[tx.parent1].append(tx.hash)
        if tx.parent2 != self.GENESIS_HASH and tx.parent2 != tx.parent1:
            self.children[tx.parent2].append(tx.hash)
        
        self.tips.add(tx.hash)
        if tx.parent1 in self.tips:
            self.tips.discard(tx.parent1)
        if tx.parent2 in self.tips:
            self.tips.discard(tx.parent2)
        
        self._update_confirmations(tx.hash)
        return True
    
    def _update_confirmations(self, new_tx_hash: str) -> None:
        parents = self.parents.get(new_tx_hash, (None, None))
        for parent in parents:
            if parent and parent != self.GENESIS_HASH:
                self.confirmations[parent] += 1
    
    def select_tips(self, count: int = 2) -> List[str]:
        available = list(self.tips)
        if not available:
            return [self.GENESIS_HASH] * count
        if len(available) <= count:
            result = available.copy()
            while len(result) < count:
                result.append(self.GENESIS_HASH)
            return result
        return random.sample(available, count)
    
    def get_confirmation_count(self, tx_hash: str) -> int:
        """Gibt Anzahl der Bestätigungen für eine Transaktion zurück"""
        if tx_hash == self.GENESIS_HASH:
            return float('inf')
        return self.confirmations.get(tx_hash, 0)
    
    def is_confirmed(self, tx_hash: str, min_confirmations: int = 3) -> bool:
        """Prüft, ob Transaktion genügend Bestätigungen hat"""
        return self.get_confirmation_count(tx_hash) >= min_confirmations
    
    def get_all_transactions(self) -> List[Transaction]:
        return list(self.transactions.values())
    
    def validate_tips(self) -> None:
        """Entfernt ungültige Tips aus der Menge"""
        valid_tips = set()
        for tip in self.tips:
            if tip == self.GENESIS_HASH or tip in self.transactions:
                valid_tips.add(tip)
        self.tips = valid_tips