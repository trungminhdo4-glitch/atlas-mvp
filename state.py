# state.py
import json
import os
from core.tangle import Tangle
from core.node import Node
from tokens.engine import TokenEngine

STATE_FILE = "atlas_state.json"

def save_state(tangle, token_engine, nodes):
    """Speichert Zustand in JSON (sehr vereinfacht)"""
    # Nur die minimal nötigen Daten speichern
    data = {
        "nodes": {addr: {"address": addr} for addr in nodes.keys()},
        "transactions": [tx.to_dict() for tx in tangle.get_all_transactions()],
        "confirmations": dict(tangle.confirmations),
        "tips": list(tangle.tips),
        "balances": token_engine.balances,
        "processed_txs": list(token_engine.processed_txs)
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_state():
    """Lädt Zustand aus JSON oder erstellt neuen"""
    if not os.path.exists(STATE_FILE):
        return Tangle(), TokenEngine(Tangle()), {}
    
    with open(STATE_FILE, 'r') as f:
        data = json.load(f)
    
    # Neuen Tangle erstellen
    tangle = Tangle()
    # Genesis separat behandeln – aber wir überspringen das für MVP
    
    # Transactions wiederherstellen (einfach: nur Hash und Bestätigungen)
    # Für echtes MVP reicht: nur Balances und Node-Adressen speichern
    nodes = {addr: None for addr in data["nodes"]}
    token_engine = TokenEngine(tangle)
    token_engine.balances = data.get("balances", {})
    token_engine.processed_txs = set(data.get("processed_txs", []))
    
    # Für Demo reicht das!
    return tangle, token_engine, nodes