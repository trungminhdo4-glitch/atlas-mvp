from typing import List, Optional
from compute.job import ComputeJob
from tokens.ledger import TokenLedger


class JobScheduler:
    def __init__(self, ledger: TokenLedger):
        self.ledger = ledger
        self.job_queue: List[ComputeJob] = []
    
    def submit_job(self, job: ComputeJob) -> bool:
        if not job.is_valid():
            return False
        if self.ledger.get_balance(job.node_id) < job.token_cost:
            return False
        self.job_queue.append(job)
        return True
    
    def get_next_job(self) -> Optional[ComputeJob]:
        if not self.job_queue:
            return None
        return self.job_queue.pop(0)
    
    def get_queue_length(self) -> int:
        return len(self.job_queue)