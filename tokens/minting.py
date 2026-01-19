from typing import List, Set
from energy.contribution import EnergyContribution
from tokens.ledger import TokenLedger


class TokenMinter:
    KWH_TO_TOKEN_RATE = 10.0
    MIN_CONFIRMATION_DEPTH = 3
    
    def __init__(self, ledger: TokenLedger):
        self.ledger = ledger
        self.processed_transactions: Set[str] = set()
    
    def mint_for_contributions(self, contributions: List[EnergyContribution]) -> List[EnergyContribution]:
        minted = []
        for contrib in contributions:
            if contrib.transaction_hash in self.processed_transactions:
                continue
            tokens = contrib.amount_kwh * self.KWH_TO_TOKEN_RATE
            self.ledger.credit_tokens(contrib.node_id, tokens)
            self.processed_transactions.add(contrib.transaction_hash)
            minted.append(contrib)
        return minted