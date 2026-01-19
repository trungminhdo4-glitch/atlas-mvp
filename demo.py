# demo.py
from core.tangle import Tangle
from core.node import Node
from tokens.engine import TokenEngine

tangle = Tangle()
token_engine = TokenEngine(tangle)
nodes = {}

node1 = Node(tangle)
nodes[node1.address] = node1
print(f"✅ Node1 erstellt: {node1.address}")

node2 = Node(tangle)
nodes[node2.address] = node2
print(f"✅ Node2 erstellt: {node2.address}")

tx1 = node1.submit_energy(50, "solar-panel")
print(f"📨 Energie gemeldet (Node1): 50 kWh → TX {tx1.hash[:8]}...")

tx2 = node2.submit_energy(30, "wind-turbine")
print(f"📨 Energie gemeldet (Node2): 30 kWh → TX {tx2.hash[:8]}...")

tx_hashes = [tx1.hash, tx2.hash]
print(f"\n🔁 Starte Bestätigungsprozess für {len(tx_hashes)} Transaktionen...")
for i in range(3):
    for tx_hash in tx_hashes:
        tangle.confirmations[tx_hash] += 1
    print(f"  Bestätigung {i+1}/3 abgeschlossen")

print("\n💰 Versuche, Tokens zu minten...")
newly_minted = token_engine.process_confirmed_transactions()
if newly_minted:
    print("✅ Tokens erfolgreich gemint:")
    for m in newly_minted:
        print(f"   {m['node'][:8]}...: +{int(m['tokens'])} tokens ({m['kwh']} kWh)")
else:
    print("ℹ️  Keine neuen Tokens gemint (evtl. bereits verarbeitet oder nicht bestätigt)")

print("\n📊 Endgültige Token-Balances:")
balances = token_engine.get_all_balances()
if balances:
    for addr, balance in balances.items():
        print(f"   {addr}: {int(balance)} tokens")
else:
    print("   Keine Balances vorhanden")
    
print("\n📈 Tangle-Statistiken:")
stats = tangle.get_stats()
print(f"   Gesamt Transactions: {stats['total_transactions']}")
print(f"   Bestätigte: {stats['confirmed_transactions']}")
print(f"   Tips: {stats['tips']}")
print(f"   Nodes: {stats['nodes']}")