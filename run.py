# run.py
from orchestration.coordinator import Coordinator
from compute.job import ComputeJob


def main():
    coord = Coordinator()
    
    # Register nodes
    node1 = coord.register_node("node_solar_01")
    node2 = coord.register_node("node_wind_02")
    
    # Submit energy
    tx1 = coord.submit_energy("node_solar_01", 50.0, "solar_panel_a")
    tx2 = coord.submit_energy("node_wind_02", 30.0, "wind_turbine_b")
    
    # Explicitly confirm both transactions 3 times
    for _ in range(3):
        if tx1 in coord.dag.transactions:
            coord.dag.confirmations[tx1] += 1
        if tx2 in coord.dag.transactions:
            coord.dag.confirmations[tx2] += 1
    
    # Mint tokens
    minted = coord.process_minting()
    print(f"Minted tokens for {len(minted)} contributions")
    
    # Submit compute job
    job = ComputeJob(
        job_id="job_001",
        node_id="node_solar_01",
        token_cost=100.0,
        payload={"task": "prime_check", "n": 982451653}
    )
    if coord.submit_compute_job(job):
        result = coord.execute_next_job()
        print("Job result:", result)
    
    # Show state
    state = coord.get_state()
    print("System state:", state)


if __name__ == "__main__":
    main()