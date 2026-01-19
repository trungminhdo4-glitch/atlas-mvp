import cmd
import atexit
from orchestration.coordinator import Coordinator
from compute.job import ComputeJob
import os


class AtlasCLI(cmd.Cmd):
    intro = "Willkommen bei Atlas Post-MVP CLI. Tippe 'help' oder '?' für Hilfe.\n"
    prompt = "(atlas) "
    
    def __init__(self):
        super().__init__()
        self.coordinator = Coordinator()
        self.current_node = None
        
        # Load existing state if available
        if self.coordinator.load_state():
            print("📥 Vorheriger Zustand geladen")
            # Try to restore current node
            if self.coordinator.nodes:
                self.current_node = next(iter(self.coordinator.nodes))
        else:
            print("🆕 Neues System gestartet")
        
        # Auto-save on exit
        atexit.register(self.coordinator.save_state)
    
    def do_create_node(self, arg):
        """Erstelle einen Node: create_node <node_id>"""
        node_id = arg.strip()
        if not node_id:
            print("❌ Fehler: Bitte gib eine Node-ID an (z.B. 'solar_farm_1')")
            return
        self.coordinator.register_node(node_id)
        print(f"✅ Node '{node_id}' erstellt und registriert.")
        if not self.current_node:
            self.current_node = node_id
            print(f"ℹ️  Aktuelle Node: {self.current_node}")
        self.coordinator.save_state()
    
    def do_set_node(self, arg):
        """Setze aktuelle Node: set_node <node_id>"""
        node_id = arg.strip()
        if not node_id:
            print("❌ Fehler: Bitte gib eine Node-ID an")
            return
        if node_id not in self.coordinator.nodes:
            print(f"❌ Fehler: Node '{node_id}' existiert nicht. Erstelle sie mit 'create_node'")
            return
        self.current_node = node_id
        print(f"✅ Aktuelle Node gesetzt: {self.current_node}")
        self.coordinator.save_state()
    
    def do_submit_energy(self, arg):
        """Melde Energie: submit_energy <kwh> <source_id>"""
        if not self.current_node:
            print("❌ Fehler: Keine aktuelle Node gesetzt. Nutze 'create_node' oder 'set_node'")
            return
        
        parts = arg.split()
        if len(parts) < 2:
            print("❌ Fehler: Nutzung: submit_energy <kwh> <source_id>")
            return
        
        try:
            kwh = float(parts[0])
            source_id = " ".join(parts[1:])
        except ValueError:
            print("❌ Fehler: kWh muss eine Zahl sein")
            return
        
        if kwh <= 0:
            print("❌ Fehler: kWh muss positiv sein")
            return
        
        try:
            tx_hash = self.coordinator.submit_energy(self.current_node, kwh, source_id)
            print(f"✅ Energie gemeldet: {kwh} kWh von Quelle '{source_id}'")
            print(f"   TX-Hash: {tx_hash[:12]}...")
            self.coordinator.save_state()
        except Exception as e:
            print(f"❌ Fehler beim Hinzufügen zur DAG: {e}")
    
    def do_confirm(self, arg):
        """Bestätige Transaktionen (simuliert Tip-Referenzierung)"""
        count = self.coordinator.confirm_transactions()
        if count > 0:
            print(f"✅ {count} Transaktion(en) bestätigt")
            self.coordinator.save_state()
        else:
            print("ℹ️  Keine Transaktionen zum Bestätigen")
    
    def do_mint(self, arg):
        """Mint Tokens für bestätigte Energie-Beiträge"""
        minted = self.coordinator.process_minting()
        if minted:
            print(f"💰 {len(minted)} Energie-Beiträge gemint:")
            for contrib in minted:
                tokens = contrib.amount_kwh * 10
                print(f"   {contrib.node_id}: +{int(tokens)} Tokens ({contrib.amount_kwh} kWh)")
            self.coordinator.save_state()
        else:
            print("ℹ️  Keine neuen Beiträge zum Minten (benötigt ≥3 Bestätigungen)")
    
    def do_submit_job(self, arg):
        """Reiche Compute-Job ein: submit_job <job_id> <token_cost> <payload>"""
        if not self.current_node:
            print("❌ Fehler: Keine aktuelle Node gesetzt")
            return
        
        parts = arg.split(maxsplit=2)
        if len(parts) < 3:
            print("❌ Fehler: Nutzung: submit_job <job_id> <token_cost> <payload>")
            return
        
        job_id = parts[0]
        try:
            token_cost = float(parts[1])
        except ValueError:
            print("❌ Fehler: token_cost muss eine Zahl sein")
            return
        
        payload_str = parts[2]
        try:
            import json
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            print("❌ Fehler: Payload muss gültiges JSON sein")
            return
        
        job = ComputeJob(
            job_id=job_id,
            node_id=self.current_node,
            token_cost=token_cost,
            payload=payload
        )
        
        if self.coordinator.submit_compute_job(job):
            print(f"✅ Job '{job_id}' eingereicht (Kosten: {token_cost} Tokens)")
            self.coordinator.save_state()
        else:
            print(f"❌ Job '{job_id}' abgelehnt (ungültig oder unzureichendes Guthaben)")
    
    def do_execute_job(self, arg):
        """Führe nächsten Job in der Warteschlange aus"""
        result = self.coordinator.execute_next_job()
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"✅ Job '{result['job_id']}' ausgeführt")
            print(f"   Ergebnis: {result.get('result', 'none')}")
            self.coordinator.save_state()
    
    def do_show_balances(self, arg):
        """Zeige Token-Balances aller Nodes"""
        balances = self.coordinator.ledger.get_all_balances()
        if not balances:
            print("ℹ️  Keine Balances vorhanden")
            return
        print("💰 Token-Balances:")
        for node_id, balance in balances.items():
            print(f"   {node_id}: {int(balance)} Tokens")
    
    def do_show_state(self, arg):
        """Zeige Systemzustand"""
        state = self.coordinator.get_state()
        print("\n📊 Systemzustand:")
        print(f"  DAG:")
        print(f"    Transaktionen: {state['dag_stats']['total_transactions']}")
        print(f"    Tips: {state['dag_stats']['tips']}")
        print(f"    Nodes: {state['dag_stats']['nodes']}")
        print(f"  Token:")
        print(f"    Gesamtversorgung: {int(state['token_stats']['total_supply'])} Tokens")
        print(f"    Token-Halter: {state['token_stats']['holders']}")
        print(f"  Compute:")
        print(f"    Warteschlange: {state['compute_stats']['queue_length']} Jobs")
    
    def do_list_nodes(self, arg):
        """Liste alle registrierten Nodes"""
        if not self.coordinator.nodes:
            print("ℹ️  Keine Nodes registriert")
            return
        print("✅ Registrierte Nodes:")
        for node_id in self.coordinator.nodes:
            marker = " ← aktuell" if node_id == self.current_node else ""
            print(f"   {node_id}{marker}")
    
    def do_quit(self, arg):
        """Beende die CLI"""
        print("💾 Speichere Zustand...")
        self.coordinator.save_state()
        print("👋 Auf Wiedersehen!")
        return True
    
    def do_exit(self, arg):
        """Beende die CLI"""
        return self.do_quit(arg)
    
    def do_clear_state(self, arg):
        """Lösche gespeicherten Zustand und starte neu"""
        if os.path.exists(self.coordinator.STATE_FILE):
            os.remove(self.coordinator.STATE_FILE)
        print("🗑️  Zustand gelöscht. Starte neu mit 'quit' und erneutem Start.")
    
    def default(self, line):
        if line.strip():
            print(f"❌ Unbekannter Befehl: '{line}'. Tippe 'help' für verfügbare Befehle.")
    
    def emptyline(self):
        pass


if __name__ == '__main__':
    AtlasCLI().cmdloop()