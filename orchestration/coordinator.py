import json
import os
from collections import defaultdict
from typing import List, Dict, Any
from core.dag import DAG
from core.node import Node
from core.transaction import Transaction
from energy.contribution import EnergyContribution
from tokens.ledger import TokenLedger
from tokens.minting import TokenMinter
from compute.scheduler import JobScheduler
from compute.executor import ComputeExecutor
from compute.job import ComputeJob


class Coordinator:
    STATE_FILE = "atlas_state.json"
    
    def __init__(self):
        self.dag = DAG()
        self.ledger = TokenLedger()
        self.minter = TokenMinter(self.ledger)
        self.scheduler = JobScheduler(self.ledger)
        self.executor = ComputeExecutor(self.ledger)
        self.nodes: Dict[str, Node] = {}
    
    def register_node(self, node_id: str) -> Node:
        if node_id in self.nodes:
            return self.nodes[node_id]
        node = Node(node_id)
        self.nodes[node_id] = node
        return node
    
    def submit_energy(
        self,
        node_id: str,
        amount_kwh: float,
        source_id: str
    ) -> str:
        node = self.register_node(node_id)
        tips = self.dag.select_tips(2)
        tx = node.create_energy_transaction(amount_kwh, source_id, tips[0], tips[1])
        success = self.dag.add_transaction(tx)
        if not success:
            raise RuntimeError("Failed to add transaction to DAG")
        return tx.hash
    
    def confirm_transactions(self) -> int:
        tips = list(self.dag.tips)
        confirmed_count = 0
        for tip in tips:
            if tip != self.dag.GENESIS_HASH:
                self.dag.confirmations[tip] += 1
                confirmed_count += 1
        return confirmed_count
    
    def process_minting(self) -> List[EnergyContribution]:
        from core.consensus import get_confirmed_transactions
        confirmed_txs = get_confirmed_transactions(self.dag, 3)
        contributions = []
        for tx in confirmed_txs:
            contrib = EnergyContribution.from_transaction(tx.hash, tx.to_dict())
            contributions.append(contrib)
        
        from energy.validator import EnergyValidator
        valid_contribs = EnergyValidator.validate_batch(contributions)
        minted = self.minter.mint_for_contributions(valid_contribs)
        return minted
    
    def submit_compute_job(self, job: 'ComputeJob') -> bool:
        return self.scheduler.submit_job(job)
    
    def execute_next_job(self) -> Dict[str, Any]:
        job = self.scheduler.get_next_job()
        if not job:
            return {"error": "no_jobs_in_queue"}
        return self.executor.execute_job(job)
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "dag_stats": {
                "total_transactions": len(self.dag.transactions),
                "tips": len(self.dag.tips),
                "nodes": len(self.nodes)
            },
            "token_stats": {
                "total_supply": self.ledger.total_supply,
                "holders": len(self.ledger.balances)
            },
            "compute_stats": {
                "queue_length": self.scheduler.get_queue_length()
            }
        }
    
    def save_state(self) -> None:
        """Persist current state to disk"""
        data = {
            "nodes": list(self.nodes.keys()),
            "balances": self.ledger.balances,
            "total_supply": self.ledger.total_supply,
            "processed_transactions": list(self.minter.processed_transactions),
            "dag": {
                "transactions": [tx.to_dict() for tx in self.dag.transactions.values()],
                "tips": list(self.dag.tips),
                "confirmations": dict(self.dag.confirmations),
                "parents": self.dag.parents
            },
            "job_queue": [
                {
                    "job_id": job.job_id,
                    "node_id": job.node_id,
                    "token_cost": job.token_cost,
                    "payload": job.payload
                }
                for job in self.scheduler.job_queue
            ]
        }
        with open(self.STATE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_state(self) -> bool:
        """Restore state from disk, return True if successful"""
        if not os.path.exists(self.STATE_FILE):
            return False
        
        with open(self.STATE_FILE, 'r') as f:
            data = json.load(f)
        
        # Clear current state
        self.dag = DAG()
        self.ledger = TokenLedger()
        self.scheduler = JobScheduler(self.ledger)
        self.executor = ComputeExecutor(self.ledger)
        self.nodes = {}
        
        # Restore nodes
        for node_id in data["nodes"]:
            self.register_node(node_id)
        
        # Restore ledger
        self.ledger.balances = data["balances"]
        self.ledger.total_supply = data["total_supply"]
        
        # Restore minter
        self.minter = TokenMinter(self.ledger)
        self.minter.processed_transactions = set(data["processed_transactions"])
        
        # Restore DAG
        dag_data = data["dag"]
        for tx_dict in dag_data["transactions"]:
            tx = Transaction(
                payload=tx_dict["payload"],
                parent1=tx_dict["parent1"],
                parent2=tx_dict["parent2"],
                node_id=tx_dict["node_id"],
                signature=tx_dict["signature"]
            )
            # Reconstruct hash (since it's derived)
            tx.hash = tx._compute_hash()
            self.dag.transactions[tx.hash] = tx
        
        self.dag.tips = set(dag_data["tips"])
        self.dag.confirmations = defaultdict(int, dag_data["confirmations"])
        self.dag.parents = dag_data["parents"]
        # Rebuild children index
        self.dag.children = defaultdict(list)
        for child_hash, (p1, p2) in self.dag.parents.items():
            if p1 != self.dag.GENESIS_HASH:
                self.dag.children[p1].append(child_hash)
            if p2 != self.dag.GENESIS_HASH and p2 != p1:
                self.dag.children[p2].append(child_hash)
        
        # Validate and repair tips
        self.dag.validate_tips()
        
        # Restore job queue
        for job_data in data["job_queue"]:
            job = ComputeJob(
                job_id=job_data["job_id"],
                node_id=job_data["node_id"],
                token_cost=job_data["token_cost"],
                payload=job_data["payload"]
            )
            self.scheduler.job_queue.append(job)
        
        return True