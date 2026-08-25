import json
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import List, Dict, Any, Tuple
from core.dag import DAG
from core.node import Node
from core.transaction import Transaction
from energy.contribution import EnergyContribution
from tokens.ledger import TokenLedger
from tokens.minting import TokenMinter
from compute.scheduler import JobScheduler
from compute.executor import ComputeExecutor
from compute.job import ComputeJob

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_STATE_SECTIONS = (
    "nodes",
    "balances",
    "total_supply",
    "processed_transactions",
    "dag",
    "job_queue",
)
_TX_FIELDS = (
    "hash",
    "payload",
    "parent1",
    "parent2",
    "node_id",
    "timestamp",
    "signature",
)


class StateCorruptionError(Exception):
    """An existing persisted state file cannot be trusted.

    Raised instead of incidental KeyError/TypeError/JSONDecodeError whenever
    an existing state file fails syntactic, structural or semantic
    validation. Loading fails closed: the Coordinator keeps its previous
    in-memory state, the offending file is left untouched on disk, and the
    failure_class attribute ("syntax", "structure" or "semantic") identifies
    the category without embedding persisted payloads in the message.
    """

    def __init__(self, failure_class: str, detail: str):
        self.failure_class = failure_class
        super().__init__(f"persisted state rejected [{failure_class}]: {detail}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and (
        isinstance(value, int) or math.isfinite(value)
    )


def _reconstruct_components(
    source_name: str, data: Any
) -> Tuple[
    DAG, TokenLedger, TokenMinter, JobScheduler, ComputeExecutor, Dict[str, Node]
]:
    """Validate a parsed state document and rebuild all components locally.

    Performs structural and semantic validation before any component is
    handed back, so callers can commit them to a live Coordinator only after
    every check passed. Raises StateCorruptionError otherwise; never mutates
    the caller's state.
    """

    def reject(failure_class: str, detail: str) -> None:
        raise StateCorruptionError(failure_class, f"{source_name}: {detail}")

    # --- structural boundary ------------------------------------------------
    if not isinstance(data, dict):
        reject("structure", "top-level document must be a JSON object")
    for section in _STATE_SECTIONS:
        if section not in data:
            reject("structure", f"missing required section '{section}'")
    if not isinstance(data["nodes"], list) or not all(
        isinstance(node_id, str) for node_id in data["nodes"]
    ):
        reject("structure", "'nodes' must be a list of node id strings")
    if not isinstance(data["balances"], dict):
        reject("structure", "'balances' must be an object")
    for holder, amount in data["balances"].items():
        if not _is_finite_number(amount):
            reject("structure", f"'balances[{holder}]' must be a finite number")
        if amount < 0:
            reject("semantic", f"'balances[{holder}]' is negative")
    if not _is_finite_number(data["total_supply"]):
        reject("structure", "'total_supply' must be a finite number")
    if data["total_supply"] < 0:
        reject("structure", "'total_supply' must be a non-negative number")
    if not isinstance(data["processed_transactions"], list) or not all(
        isinstance(tx_hash, str) for tx_hash in data["processed_transactions"]
    ):
        reject(
            "structure",
            "'processed_transactions' must be a list of transaction hashes",
        )
    dag_data = data["dag"]
    if not isinstance(dag_data, dict):
        reject("structure", "'dag' must be an object")
    for subsection in ("transactions", "tips", "confirmations", "parents"):
        if subsection not in dag_data:
            reject("structure", f"missing required dag section '{subsection}'")
    if not isinstance(dag_data["transactions"], list):
        reject("structure", "'dag.transactions' must be a list")
    if not isinstance(dag_data["tips"], list):
        reject("structure", "'dag.tips' must be a list")
    if not isinstance(dag_data["confirmations"], dict):
        reject("structure", "'dag.confirmations' must be an object")
    if not isinstance(dag_data["parents"], dict):
        reject("structure", "'dag.parents' must be an object")
    if not isinstance(data["job_queue"], list):
        reject("structure", "'job_queue' must be a list")

    # --- transaction records: structure + canonical identity -----------------
    genesis = DAG.GENESIS_HASH
    transactions: Dict[str, Transaction] = {}
    parents_map: Dict[str, Tuple[str, str]] = {}
    for index, tx_dict in enumerate(dag_data["transactions"]):
        if not isinstance(tx_dict, dict):
            reject("structure", f"dag.transactions[{index}] must be an object")
        for field in _TX_FIELDS:
            if field not in tx_dict:
                reject(
                    "structure",
                    f"dag.transactions[{index}] is missing field '{field}'",
                )
        if not isinstance(tx_dict["payload"], dict):
            reject("structure", f"dag.transactions[{index}].payload must be an object")
        if not isinstance(tx_dict["timestamp"], int) or isinstance(
            tx_dict["timestamp"], bool
        ):
            reject(
                "structure",
                f"dag.transactions[{index}].timestamp must be an integer",
            )
        if tx_dict["signature"] is not None and not isinstance(
            tx_dict["signature"], str
        ):
            reject(
                "structure",
                f"dag.transactions[{index}].signature must be a string or null",
            )
        tx = Transaction(
            payload=tx_dict["payload"],
            parent1=tx_dict["parent1"],
            parent2=tx_dict["parent2"],
            node_id=tx_dict["node_id"],
            signature=tx_dict["signature"],
        )
        tx.timestamp = tx_dict["timestamp"]
        tx.hash = tx._compute_hash()
        if tx.hash != tx_dict["hash"]:
            reject(
                "semantic",
                f"dag.transactions[{index}]: stored hash does not match "
                "canonical identity of the persisted fields",
            )
        if tx.hash in transactions:
            reject("semantic", "duplicate transaction identity in dag.transactions")
        transactions[tx.hash] = tx

    tx_hashes = set(transactions)

    # --- graph references ----------------------------------------------------
    if set(dag_data["parents"]) != tx_hashes:
        reject(
            "semantic",
            "'dag.parents' keys do not match the persisted transaction set",
        )
    for child_hash, refs in dag_data["parents"].items():
        if (
            not isinstance(refs, list)
            or len(refs) != 2
            or not all(isinstance(ref, str) for ref in refs)
        ):
            reject(
                "semantic",
                f"dag.parents[{child_hash}] must be a pair of parent hashes",
            )
        parent1, parent2 = refs
        tx = transactions[child_hash]
        if (parent1, parent2) != (tx.parent1, tx.parent2):
            reject(
                "semantic",
                f"dag.parents[{child_hash}] disagrees with transaction parents",
            )
        for ref in (parent1, parent2):
            if ref != genesis and ref not in tx_hashes:
                reject(
                    "semantic",
                    f"dag.parents[{child_hash}] references unknown transaction",
                )
        parents_map[child_hash] = (parent1, parent2)

    for tip in dag_data["tips"]:
        if not isinstance(tip, str) or (tip != genesis and tip not in tx_hashes):
            reject("semantic", "'dag.tips' references an unknown transaction")

    for tx_hash, count in dag_data["confirmations"].items():
        if tx_hash not in tx_hashes:
            reject(
                "semantic",
                "'dag.confirmations' contains an unknown transaction",
            )
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            reject(
                "semantic",
                f"'dag.confirmations[{tx_hash}]' must be a non-negative integer",
            )

    for tx_hash in data["processed_transactions"]:
        if tx_hash not in tx_hashes:
            reject(
                "semantic",
                "'processed_transactions' contains an unknown transaction",
            )

    # --- token conservation ---------------------------------------------------
    balance_sum = math.fsum(data["balances"].values())
    if not math.isclose(
        data["total_supply"], balance_sum, rel_tol=1e-09, abs_tol=1e-09
    ):
        reject(
            "semantic",
            "'total_supply' disagrees with the sum of persisted balances",
        )

    # --- job queue ------------------------------------------------------------
    job_queue_data = []
    for index, job_data in enumerate(data["job_queue"]):
        if not isinstance(job_data, dict):
            reject("structure", f"job_queue[{index}] must be an object")
        for field in ("job_id", "node_id"):
            if not isinstance(job_data.get(field), str):
                reject(
                    "structure",
                    f"job_queue[{index}].{field} must be a string",
                )
        if not _is_finite_number(job_data.get("token_cost")):
            reject(
                "structure",
                f"job_queue[{index}].token_cost must be a finite number",
            )
        if not isinstance(job_data.get("payload"), dict):
            reject(
                "structure",
                f"job_queue[{index}].payload must be an object",
            )
        job_queue_data.append(job_data)

    # --- local assembly (no live state touched yet) ----------------------------
    dag = DAG()
    dag.transactions = transactions
    dag.parents = parents_map
    dag.tips = set(dag_data["tips"])
    dag.confirmations = defaultdict(int, dag_data["confirmations"])
    dag.children = defaultdict(list)
    for child_hash, (parent1, parent2) in parents_map.items():
        if parent1 != genesis:
            dag.children[parent1].append(child_hash)
        if parent2 != genesis and parent2 != parent1:
            dag.children[parent2].append(child_hash)
    dag.validate_tips()

    ledger = TokenLedger()
    ledger.balances = dict(data["balances"])
    ledger.total_supply = data["total_supply"]

    minter = TokenMinter(ledger)
    minter.processed_transactions = set(data["processed_transactions"])

    scheduler = JobScheduler(ledger)
    executor = ComputeExecutor(ledger)
    for job_data in job_queue_data:
        scheduler.job_queue.append(
            ComputeJob(
                job_id=job_data["job_id"],
                node_id=job_data["node_id"],
                token_cost=job_data["token_cost"],
                payload=job_data["payload"],
            )
        )

    nodes = {node_id: Node(node_id) for node_id in data["nodes"]}
    return dag, ledger, minter, scheduler, executor, nodes


class Coordinator:
    STATE_FILE = str(PROJECT_ROOT / "atlas_state.json")

    def __init__(self):
        self.dag = DAG()
        self.ledger = TokenLedger()
        self.minter = TokenMinter(self.ledger)
        self.scheduler = JobScheduler(self.ledger)
        self.executor = ComputeExecutor(self.ledger)
        self.nodes: Dict[str, Node] = {}
        self._job_execution_lock = Lock()

    def register_node(self, node_id: str) -> Node:
        if node_id in self.nodes:
            return self.nodes[node_id]
        node = Node(node_id)
        self.nodes[node_id] = node
        return node

    def submit_energy(self, node_id: str, amount_kwh: float, source_id: str) -> str:
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

    def submit_compute_job(self, job: "ComputeJob") -> bool:
        return self.scheduler.submit_job(job)

    def execute_next_job(self) -> Dict[str, Any]:
        with self._job_execution_lock:
            job = self.scheduler.peek_next_job()
            if not job:
                return {"error": "no_jobs_in_queue"}
            result = self.executor.execute_job(job)
            if result.get("status") == "completed":
                if not self.scheduler.complete_job(job):
                    raise RuntimeError("Completed job is no longer at the queue head")
            return result

    def get_state(self) -> Dict[str, Any]:
        return {
            "dag_stats": {
                "total_transactions": len(self.dag.transactions),
                "tips": len(self.dag.tips),
                "nodes": len(self.nodes),
            },
            "token_stats": {
                "total_supply": self.ledger.total_supply,
                "holders": len(self.ledger.balances),
            },
            "compute_stats": {"queue_length": self.scheduler.get_queue_length()},
        }

    def save_state(self) -> None:
        """Persist current state to disk.

        Writes a complete replacement to a same-directory temporary file and
        atomically swaps it into place, so a failed or interrupted save leaves
        the previous valid state intact. The destination is either the old or
        the new complete state, never partial content.
        """
        data = {
            "nodes": list(self.nodes.keys()),
            "balances": self.ledger.balances,
            "total_supply": self.ledger.total_supply,
            "processed_transactions": list(self.minter.processed_transactions),
            "dag": {
                "transactions": [tx.to_dict() for tx in self.dag.transactions.values()],
                "tips": list(self.dag.tips),
                "confirmations": dict(self.dag.confirmations),
                "parents": self.dag.parents,
            },
            "job_queue": [
                {
                    "job_id": job.job_id,
                    "node_id": job.node_id,
                    "token_cost": job.token_cost,
                    "payload": job.payload,
                }
                for job in self.scheduler.job_queue
            ],
        }
        state_path = Path(self.STATE_FILE)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(state_path.parent), prefix=".atlas_state-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, state_path)
        except BaseException:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
            raise

    def load_state(self) -> bool:
        """Restore state from disk, return True if successful.

        A missing state file is a legitimate first run and returns False
        without touching this instance. An existing file that fails syntax,
        structure or semantic validation raises StateCorruptionError; in that
        case this instance keeps its complete previous in-memory state, the
        offending file is left byte-for-byte unchanged, and no component of
        this Coordinator is replaced. Reconstructed components are committed
        to this instance only after every validation step passed.
        """
        if not os.path.exists(self.STATE_FILE):
            return False

        try:
            with open(self.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StateCorruptionError(
                "syntax", f"{Path(self.STATE_FILE).name}: {exc}"
            ) from exc

        (
            dag,
            ledger,
            minter,
            scheduler,
            executor,
            nodes,
        ) = _reconstruct_components(Path(self.STATE_FILE).name, data)

        # Commit point: validation fully passed, swap in the new components.
        self.dag = dag
        self.ledger = ledger
        self.minter = minter
        self.scheduler = scheduler
        self.executor = executor
        self.nodes = nodes
        return True
