import threading
import unittest

from compute.job import ComputeJob
from orchestration.coordinator import Coordinator
from tokens.ledger import TokenLedger


class TokenLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.coord = Coordinator()

    def _confirmed_contribution(
        self, node_id="solar_1", kwh=5.0, source="solar_a", confirms=3
    ):
        tx_hash = self.coord.submit_energy(node_id, kwh, source)
        for _ in range(confirms):
            self.coord.confirm_transactions()
        return tx_hash

    def test_end_to_end_mint_credits_exact_amount_once(self):
        self._confirmed_contribution()
        minted = self.coord.process_minting()
        self.assertEqual(len(minted), 1)
        self.assertEqual(self.coord.ledger.get_balance("solar_1"), 50.0)
        self.assertEqual(self.coord.ledger.total_supply, 50.0)

    def test_mint_is_idempotent_under_replay(self):
        self._confirmed_contribution()
        first = self.coord.process_minting()
        second = self.coord.process_minting()
        third = self.coord.process_minting()
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(third, [])
        self.assertEqual(self.coord.ledger.get_balance("solar_1"), 50.0)

    def test_below_threshold_not_minted_until_third_confirmation(self):
        self._confirmed_contribution(confirms=2)
        self.assertEqual(self.coord.process_minting(), [])
        self.coord.confirm_transactions()
        minted = self.coord.process_minting()
        self.assertEqual(len(minted), 1)
        self.assertEqual(self.coord.ledger.total_supply, 50.0)

    def test_non_renewable_source_filtered_from_minting(self):
        self._confirmed_contribution(source="battery_backup")
        self.assertEqual(self.coord.process_minting(), [])
        self.assertEqual(self.coord.ledger.total_supply, 0.0)

    def test_ledger_conservation_across_credit_debit_cycle(self):
        ledger = TokenLedger()
        ledger.credit_tokens("a", 500.0)
        self.assertTrue(ledger.debit_tokens("a", 200.0))
        self.assertEqual(ledger.total_supply, sum(ledger.balances.values()))
        ledger.credit_tokens("b", 75.5)
        self.assertTrue(ledger.debit_tokens("a", 300.0))
        self.assertEqual(ledger.total_supply, sum(ledger.balances.values()))
        self.assertEqual(ledger.total_supply, 75.5)

    def test_debit_refusal_leaves_state_unchanged(self):
        ledger = TokenLedger()
        ledger.credit_tokens("a", 100.0)
        self.assertFalse(ledger.debit_tokens("a", 100.01))
        self.assertFalse(ledger.debit_tokens("a", 0))
        self.assertFalse(ledger.debit_tokens("a", -5.0))
        self.assertEqual(ledger.get_balance("a"), 100.0)
        self.assertEqual(ledger.total_supply, 100.0)

    def test_non_finite_debit_refusal_leaves_state_unchanged(self):
        for amount in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(amount=amount):
                ledger = TokenLedger()
                ledger.credit_tokens("a", 100.0)
                self.assertFalse(ledger.debit_tokens("a", amount))
                self.assertEqual(ledger.get_balance("a"), 100.0)
                self.assertEqual(ledger.total_supply, 100.0)

    def test_job_submission_refused_without_balance(self):
        job = ComputeJob(job_id="j1", node_id="n1", token_cost=10.0, payload={"t": 1})
        self.assertFalse(self.coord.submit_compute_job(job))
        result = self.coord.execute_next_job()
        self.assertEqual(result, {"error": "no_jobs_in_queue"})

    def test_non_finite_job_costs_are_refused_on_submission(self):
        self.coord.ledger.credit_tokens("n1", 100.0)
        for cost in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(cost=cost):
                job = ComputeJob(
                    job_id="invalid", node_id="n1", token_cost=cost, payload={}
                )
                self.assertFalse(job.is_valid())
                self.assertFalse(self.coord.submit_compute_job(job))

        self.assertEqual(self.coord.scheduler.get_queue_length(), 0)
        self.assertEqual(self.coord.ledger.get_balance("n1"), 100.0)
        self.assertEqual(self.coord.ledger.total_supply, 100.0)

    def test_executed_job_burns_exactly_token_cost(self):
        self.coord.register_node("n1")
        self.coord.ledger.credit_tokens("n1", 100.0)
        job = ComputeJob(
            job_id="j1", node_id="n1", token_cost=30.0, payload={"task": "x"}
        )
        self.assertTrue(self.coord.submit_compute_job(job))
        result = self.coord.execute_next_job()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.coord.ledger.get_balance("n1"), 70.0)
        self.assertEqual(
            self.coord.ledger.total_supply, sum(self.coord.ledger.balances.values())
        )

    def test_insufficient_balance_preserves_fifo_job_until_funded(self):
        self.coord.register_node("n1")
        self.coord.ledger.credit_tokens("n1", 100.0)
        first = ComputeJob("j1", "n1", 60.0, {"task": "first"})
        second = ComputeJob("j2", "n1", 60.0, {"task": "second"})
        third = ComputeJob("j3", "n1", 10.0, {"task": "third"})

        self.assertTrue(self.coord.submit_compute_job(first))
        self.assertTrue(self.coord.submit_compute_job(second))
        self.assertTrue(self.coord.submit_compute_job(third))
        self.assertEqual(self.coord.execute_next_job()["job_id"], "j1")
        self.assertEqual(
            [job.job_id for job in self.coord.scheduler.job_queue], ["j2", "j3"]
        )

        expected_error = {"error": "insufficient_balance", "job_id": "j2"}
        self.assertEqual(self.coord.execute_next_job(), expected_error)
        self.assertEqual(self.coord.execute_next_job(), expected_error)
        self.assertEqual(
            [job.job_id for job in self.coord.scheduler.job_queue], ["j2", "j3"]
        )
        self.assertEqual(self.coord.ledger.get_balance("n1"), 40.0)

        self.coord.ledger.credit_tokens("n1", 30.0)
        result = self.coord.execute_next_job()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["job_id"], "j2")
        self.assertEqual(self.coord.execute_next_job()["job_id"], "j3")
        self.assertEqual(self.coord.scheduler.job_queue, [])
        self.assertEqual(self.coord.execute_next_job(), {"error": "no_jobs_in_queue"})
        self.assertEqual(self.coord.ledger.get_balance("n1"), 0.0)

    def test_concurrent_callers_execute_and_debit_head_only_once(self):
        self.coord.ledger.credit_tokens("n1", 100.0)
        job = ComputeJob("j1", "n1", 30.0, {"task": "once"})
        self.assertTrue(self.coord.submit_compute_job(job))

        original_execute = self.coord.executor.execute_job
        first_execution_started = threading.Event()
        release_first_execution = threading.Event()
        duplicate_execution_started = threading.Event()
        second_call_started = threading.Event()
        state_lock = threading.Lock()
        execution_calls = 0
        results = []
        errors = []

        def controlled_execute(next_job):
            nonlocal execution_calls
            with state_lock:
                execution_calls += 1
                call_number = execution_calls
            if call_number == 1:
                first_execution_started.set()
                if not release_first_execution.wait(5):
                    raise TimeoutError("test did not release the first execution")
            else:
                duplicate_execution_started.set()
            return original_execute(next_job)

        def execute(started=None):
            if started:
                started.set()
            try:
                result = self.coord.execute_next_job()
                with state_lock:
                    results.append(result)
            except BaseException as exc:
                with state_lock:
                    errors.append(exc)

        self.coord.executor.execute_job = controlled_execute
        first_caller = threading.Thread(target=execute)
        second_caller = threading.Thread(target=execute, args=(second_call_started,))
        first_caller.start()
        try:
            self.assertTrue(first_execution_started.wait(2))
            second_caller.start()
            self.assertTrue(second_call_started.wait(2))
            duplicate_before_release = duplicate_execution_started.wait(0.5)
        finally:
            release_first_execution.set()
            first_caller.join(5)
            if second_caller.ident is not None:
                second_caller.join(5)

        self.assertFalse(duplicate_before_release)
        self.assertFalse(first_caller.is_alive())
        self.assertFalse(second_caller.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(execution_calls, 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(result.get("status") == "completed" for result in results), 1)
        self.assertIn({"error": "no_jobs_in_queue"}, results)
        self.assertEqual(self.coord.ledger.get_balance("n1"), 70.0)
        self.assertEqual(self.coord.ledger.total_supply, 70.0)
        self.assertEqual(self.coord.scheduler.job_queue, [])

    def test_payload_processing_failure_retains_fifo_without_debit(self):
        class ExplodingValue:
            def __repr__(self):
                raise RuntimeError("payload rendering failed")

        self.coord.ledger.credit_tokens("n1", 100.0)
        first = ComputeJob("j1", "n1", 30.0, {"value": ExplodingValue()})
        second = ComputeJob("j2", "n1", 10.0, {"task": "second"})
        self.assertTrue(self.coord.submit_compute_job(first))
        self.assertTrue(self.coord.submit_compute_job(second))

        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "payload rendering failed"):
                self.coord.execute_next_job()
            self.assertEqual(
                [job.job_id for job in self.coord.scheduler.job_queue], ["j1", "j2"]
            )
            self.assertEqual(self.coord.ledger.get_balance("n1"), 100.0)
            self.assertEqual(self.coord.ledger.total_supply, 100.0)

    def test_full_cycle_conservation_mint_then_spend(self):
        self._confirmed_contribution(kwh=12.0)
        self.coord.process_minting()
        self.assertEqual(self.coord.ledger.total_supply, 120.0)
        job = ComputeJob(
            job_id="j2", node_id="solar_1", token_cost=45.0, payload={"n": 1}
        )
        self.assertTrue(self.coord.submit_compute_job(job))
        self.coord.execute_next_job()
        self.assertEqual(self.coord.ledger.get_balance("solar_1"), 75.0)
        self.assertEqual(
            self.coord.ledger.total_supply, sum(self.coord.ledger.balances.values())
        )


if __name__ == "__main__":
    unittest.main()
