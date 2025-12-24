from core.crypto import Wallet
from core.transaction import EnergyTransaction


class Node:
    """Energienode im Atlas Netzwerk"""
    
    def __init__(self, tangle):
        self.tangle = tangle
        self.wallet = Wallet()
        self.address = self.wallet.get_address()
        self.balance = 0
    
    def submit_energy(self, amount_kwh, source_id):
        """Meldet Energieüberschuss"""
        if amount_kwh <= 0:
            raise ValueError("Menge muss positiv sein")
        
        tips = self.tangle.select_tips(count=2)
        
        tx = EnergyTransaction(
            amount_kwh=amount_kwh,
            source_id=source_id,
            node_address=self.address,
            parent1=tips[0],
            parent2=tips[1]
        )
        
        tx.signature = self.wallet.sign(tx.to_dict())
        
        success, message = self.tangle.add_transaction(tx)
        
        if not success:
            raise RuntimeError(f"Fehler beim Hinzufügen: {message}")
        
        return tx
    
    def get_address(self):
        return self.address
    
    def set_balance(self, amount):
        self.balance = amount