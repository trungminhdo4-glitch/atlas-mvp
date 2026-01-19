import hashlib
from typing import Any, Dict
from compute.job import ComputeJob
from tokens.ledger import TokenLedger


class ComputeExecutor:
    def __init__(self, ledger: TokenLedger):
        self.ledger = ledger
    
    def execute_job(self, job: ComputeJob) -> Dict[str, Any]:
        if not self.ledger.debit_tokens(job.node_id, job.token_cost):
            return {"error": "insufficient_balance", "job_id": job.job_id}
        
        # DETERMINISTISCHER HASH (über Prozess-Neustarts hinweg konsistent)
        if isinstance(job.payload, dict):
            payload_str = str(sorted(job.payload.items()))
        else:
            payload_str = str(job.payload)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        result_value = int(payload_hash[:8], 16) % 1000000
        
        result = {
            "job_id": job.job_id,
            "node_id": job.node_id,
            "status": "completed",
            "result": result_value
        }
        return result