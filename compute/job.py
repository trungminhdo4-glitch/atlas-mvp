from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ComputeJob:
    job_id: str
    node_id: str
    token_cost: float
    payload: Dict[str, Any]
    
    def is_valid(self) -> bool:
        return (
            bool(self.job_id) and
            bool(self.node_id) and
            self.token_cost > 0 and
            isinstance(self.payload, dict)
        )