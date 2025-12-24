# 🌍 Atlas MVP

> Ein minimalistisches, dezentrales Energiehandelssystem basierend auf einem **Directed Acyclic Graph (DAG)**.  
> Nodes melden überschüssige Energie und erhalten dafür **Token-Belohnungen** – alles in reinem Python.

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

---

## 🌟 Konzept

Atlas MVP demonstriert, wie erneuerbare Energieerzeuger (z. B. private Solaranlagen) ihre Überschüsse **dezentral und transparent** melden können – ohne zentrale Autorität.

- Jede **Energiemeldung** wird als **Transaktion** im DAG gespeichert.
- Transaktionen werden durch neue Transaktionen **bestätigt** (Tip-Selection).
- Nach **3 Bestätigungen** werden **Tokens** an den Node ausgezahlt (1 kWh = 10 Tokens).
- Alles basiert auf **kryptografischen Signaturen** (ed25519).

💡 **Ziel**: Ein verständliches, ausführbares Modell – kein produktionsreifes System.

---

## 📦 Installation

```bash
git clone https://github.com/your-name/atlas-mvp.git
cd atlas-mvp
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install -r requirements.txt