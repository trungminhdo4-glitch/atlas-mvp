from typing import List, Set
from core.transaction import Transaction
from core.dag import DAG


def get_confirmed_transactions(dag: DAG, min_depth: int = 3) -> List[Transaction]:
    confirmed = []
    for tx_hash, tx in dag.transactions.items():
        if dag.get_confirmation_depth(tx_hash) >= min_depth:
            confirmed.append(tx)
    return confirmed


def get_unconfirmed_transactions(dag: DAG, min_depth: int = 3) -> List[Transaction]:
    unconfirmed = []
    for tx_hash, tx in dag.transactions.items():
        if dag.get_confirmation_depth(tx_hash) < min_depth:
            unconfirmed.append(tx)
    return unconfirmed