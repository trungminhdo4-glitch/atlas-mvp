class TokenEngine:
    """Mintet Tokens für bestätigte Energie-Meldungen"""
    
    KWH_TO_TOKEN_RATE = 10
    MIN_CONFIRMATIONS = 3
    
    def __init__(self, tangle):
        self.tangle = tangle
        self.balances = {}
        self.processed_txs = set()
    
    def process_confirmed_transactions(self):
        confirmed = self.tangle.get_confirmed_transactions(self.MIN_CONFIRMATIONS)
        
        newly_minted = []
        
        for tx in confirmed:
            if tx.hash in self.processed_txs:
                continue
            
            if not tx.is_energy_contribution():
                continue
            
            amount_kwh = tx.get_energy_amount()
            tokens = amount_kwh * self.KWH_TO_TOKEN_RATE
            
            current_balance = self.balances.get(tx.node_address, 0)
            self.balances[tx.node_address] = current_balance + tokens
            
            self.processed_txs.add(tx.hash)
            
            newly_minted.append({
                "tx_hash": tx.hash,
                "node": tx.node_address,
                "kwh": amount_kwh,
                "tokens": tokens
            })
        
        return newly_minted
    
    def get_balance(self, address):
        return self.balances.get(address, 0)
    
    def get_all_balances(self):
        return self.balances.copy()
    
    def get_stats(self):
        total_supply = sum(self.balances.values())
        
        return {
            "total_minted_txs": len(self.processed_txs),
            "total_token_holders": len(self.balances),
            "total_supply": total_supply
        }