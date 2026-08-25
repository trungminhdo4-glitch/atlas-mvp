import json
import os
import tempfile
import unittest
from pathlib import Path

from compute.job import ComputeJob
from orchestration.coordinator import (
    PROJECT_ROOT,
    Coordinator,
    StateCorruptionError,
)


class FailingJsonModule:
    """Module stand-in whose dump() writes a partial document, then fails."""

    def __init__(self, failure):
        self.failure = failure

    def dump(self, obj, fh, indent=None):
        fh.write('{"nodes": ["n1"')
        fh.flush()
        raise self.failure


class CoordinatorPersistenceTest(unittest.TestCase):
    """Persistence boundary regression coverage.

    Every test isolates state inside a disposable temp directory; the
    repository's real atlas_state.json is never read or written.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.state_dir = Path(tmp.name)
        self.state_file = self.state_dir / "state.json"
        self.coord = Coordinator()
        self.coord.STATE_FILE = str(self.state_file)
        self._populate(self.coord)

    def _populate(self, coord):
        coord.register_node("n1")
        coord.register_node("n2")
        coord.submit_energy("n1", 50.0, "solar_a")
        for _ in range(3):
            coord.confirm_transactions()
        coord.submit_energy("n2", 30.0, "wind_b")
        for _ in range(3):
            coord.confirm_transactions()
        coord.process_minting()
        first = ComputeJob(
            job_id="j1", node_id="n1", token_cost=20.0, payload={"task": "a"}
        )
        second = ComputeJob(
            job_id="j2", node_id="n1", token_cost=5.0, payload={"task": "b"}
        )
        self.assertTrue(coord.submit_compute_job(first))
        self.assertTrue(coord.submit_compute_job(second))

    def _snapshot(self, coord):
        return {
            "nodes": set(coord.nodes),
            "balances": dict(coord.ledger.balances),
            "total_supply": coord.ledger.total_supply,
            "processed": set(coord.minter.processed_transactions),
            "hashes": set(coord.dag.transactions),
            "tips": set(coord.dag.tips),
            "confirmations": dict(coord.dag.confirmations),
            "queue": [
                (j.job_id, j.node_id, j.token_cost, j.payload)
                for j in coord.scheduler.job_queue
            ],
        }

    def _load_fresh(self):
        fresh = Coordinator()
        fresh.STATE_FILE = str(self.state_file)
        self.assertTrue(fresh.load_state())
        return fresh

    def test_round_trip_preserves_identity_and_semantics(self):
        self.coord.save_state()
        before = self._snapshot(self.coord)
        after = self._snapshot(self._load_fresh())
        self.assertDictEqual(before, after)

    def test_insufficient_balance_queue_survives_restart_and_later_executes(self):
        coord = Coordinator()
        coord.STATE_FILE = str(self.state_file)
        coord.register_node("payer")
        coord.ledger.credit_tokens("payer", 100.0)
        first = ComputeJob("costly-1", "payer", 60.0, {"task": "first"})
        second = ComputeJob("costly-2", "payer", 60.0, {"task": "second"})
        third = ComputeJob("cheap-3", "payer", 10.0, {"task": "third"})
        self.assertTrue(coord.submit_compute_job(first))
        self.assertTrue(coord.submit_compute_job(second))
        self.assertTrue(coord.submit_compute_job(third))

        self.assertEqual(coord.execute_next_job()["job_id"], "costly-1")
        self.assertEqual(
            coord.execute_next_job(),
            {"error": "insufficient_balance", "job_id": "costly-2"},
        )
        coord.save_state()

        restarted = self._load_fresh()
        self.assertEqual(
            [job.job_id for job in restarted.scheduler.job_queue],
            ["costly-2", "cheap-3"],
        )
        self.assertEqual(restarted.ledger.get_balance("payer"), 40.0)
        restarted.ledger.credit_tokens("payer", 30.0)
        result = restarted.execute_next_job()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["job_id"], "costly-2")
        self.assertEqual(restarted.execute_next_job()["job_id"], "cheap-3")
        self.assertEqual(restarted.scheduler.job_queue, [])

        restarted.save_state()
        completed = self._load_fresh()
        self.assertEqual(completed.scheduler.job_queue, [])
        self.assertEqual(completed.execute_next_job(), {"error": "no_jobs_in_queue"})

    def test_reload_does_not_remint_processed_contributions(self):
        self.coord.save_state()
        supply_before = self.coord.ledger.total_supply
        fresh = self._load_fresh()
        for _ in range(3):
            fresh.confirm_transactions()
        self.assertEqual(fresh.process_minting(), [])
        self.assertEqual(fresh.ledger.total_supply, supply_before)

    def test_failed_save_preserves_last_known_good_state(self):
        self.coord.save_state()
        good_bytes = self.state_file.read_bytes()

        import orchestration.coordinator as coord_mod

        real_json = coord_mod.json
        coord_mod.json = FailingJsonModule(RuntimeError("mid-dump failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.coord.save_state()
        finally:
            coord_mod.json = real_json

        self.assertEqual(self.state_file.read_bytes(), good_bytes)
        restored = self._snapshot(self._load_fresh())
        self.assertDictEqual(restored, self._snapshot(self.coord))

    def test_failed_save_leaves_no_temp_files_behind(self):
        self.coord.save_state()
        import orchestration.coordinator as coord_mod

        real_json = coord_mod.json
        coord_mod.json = FailingJsonModule(RuntimeError("mid-dump failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.coord.save_state()
        finally:
            coord_mod.json = real_json

        leftovers = list(self.state_dir.glob(".atlas_state-*.tmp"))
        self.assertEqual(leftovers, [])

    def test_repeated_saves_produce_identical_content(self):
        self.coord.save_state()
        first = self.state_file.read_bytes()
        self.coord.save_state()
        second = self.state_file.read_bytes()
        self.assertEqual(first, second)

    def test_corrupt_json_raises_stable_error_and_preserves_file_bytes(self):
        corrupt = b'{"nodes": ["n1", BROKEN'
        self.state_file.write_bytes(corrupt)
        with self.assertRaises(StateCorruptionError) as ctx:
            self.coord.load_state()
        self.assertEqual(ctx.exception.failure_class, "syntax")
        self.assertEqual(self.state_file.read_bytes(), corrupt)

    def test_load_without_state_file_reports_fresh_start(self):
        fresh = Coordinator()
        fresh.STATE_FILE = str(self.state_dir / "never_written.json")
        self.assertFalse(fresh.load_state())

    def test_default_state_location_is_cwd_independent(self):
        expected = PROJECT_ROOT / "atlas_state.json"
        original_cwd = os.getcwd()
        try:
            os.chdir(self.state_dir)
            self.assertEqual(Path(Coordinator().STATE_FILE), expected)
        finally:
            os.chdir(original_cwd)

    def test_save_into_missing_directory_preserves_existing_state_elsewhere(self):
        self.coord.save_state()
        good_bytes = self.state_file.read_bytes()
        self.coord.STATE_FILE = str(self.state_dir / "missing_sub" / "state.json")
        with self.assertRaises(FileNotFoundError):
            self.coord.save_state()
        self.assertEqual(self.state_file.read_bytes(), good_bytes)

    def test_saved_schema_keys_are_stable(self):
        self.coord.save_state()
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            set(data),
            {
                "nodes",
                "balances",
                "total_supply",
                "processed_transactions",
                "dag",
                "job_queue",
            },
        )
        self.assertEqual(
            set(data["dag"]),
            {"transactions", "tips", "confirmations", "parents"},
        )


if __name__ == "__main__":
    unittest.main()
