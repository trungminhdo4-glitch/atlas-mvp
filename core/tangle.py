import random
from collections import defaultdict


class Tangle:
    """Dezentraler DAG für Transactions"""
    
    GENESIS_HASH = "0" * 64
    
    def __init__(self):
        self.transactions = {}  # hash -> Transaction
        self.tips = {self.GENESIS_HASH}  # Unbestätigte Transactions
        self.children = defaultdict(list)  # parent_hash -> [child_hashes]
        self.parents = {}  # tx_hash -> (parent1, parent2)
        self.confirmations = defaultdict(int)  # tx_hash -> count
    
    def add_transaction(self, tx):
        """Fügt Transaction zum Tangle hinzu"""
        if tx.hash in self.transactions:
            return False, "Transaction existiert bereits"
        
        if tx.parent1 != self.GENESIS_HASH and tx.parent1 not in self.transactions:
            return False, f"Parent1 nicht gefunden"
        if tx.parent2 != self.GENESIS_HASH and tx.parent2 not in self.transactions:
            return False, f"Parent2 nicht gefunden"
        
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
        
        return True, "Transaction hinzugefügt"
    
    def _update_confirmations(self, new_tx_hash):
        parents = self.parents.get(new_tx_hash, (None, None))
        for parent in parents:
            if parent and parent != self.GENESIS_HASH:
                self.confirmations[parent] += 1
    
    def select_tips(self, count=2):
        available_tips = list(self.tips)
        
        if not available_tips:
            return [self.GENESIS_HASH] * count
        
        if len(available_tips) <= count:
            result = available_tips.copy()
            while len(result) < count:
                result.append(self.GENESIS_HASH)
            return result
        
        return random.sample(available_tips, count)
    
    def get_confirmed_transactions(self, min_confirmations=3):
        confirmed = []
        for tx_hash, tx in self.transactions.items():
            if tx_hash == self.GENESIS_HASH:
                continue
            if self.confirmations.get(tx_hash, 0) >= min_confirmations:
                confirmed.append(tx)
        return confirmed
    
    def is_confirmed(self, tx_hash, min_confirmations=3):
        if tx_hash == self.GENESIS_HASH:
            return True
        return self.confirmations.get(tx_hash, 0) >= min_confirmations
    
    def get_transaction(self, tx_hash):
        return self.transactions.get(tx_hash)
    
    def get_all_transactions(self):
        return list(self.transactions.values())
    
    def get_stats(self):
        """Statistiken – KORRIGIERT: Kein -1 mehr!"""
        total = len(self.transactions)  # Nur echte TXs, Genesis nicht enthalten
        confirmed = len(self.get_confirmed_transactions())
        
        return {
            "total_transactions": total,
            "confirmed_transactions": confirmed,
            "tips": len(self.tips),
            "nodes": len(set(tx.node_address for tx in self.transactions.values()))
        }