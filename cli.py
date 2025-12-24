import click
from core.tangle import Tangle
from core.node import Node
from tokens.engine import TokenEngine

tangle = Tangle()
token_engine = TokenEngine(tangle)
nodes = {}


@click.group()
def cli():
    """Atlas MVP - Command Line Interface"""
    pass


@cli.command()
@click.option('--name', default='node1', help='Node Name')
def create_node(name):
    node = Node(tangle)
    nodes[node.address] = node
    click.echo(f"✅ Node erstellt: {name}")
    click.echo(f"   Adresse: {node.address}")
    click.echo(f"   (Merke dir die Adresse!)")


@cli.command()
@click.option('--node', required=True, help='Node-Adresse')
@click.option('--kwh', required=True, type=float, help='Energiemenge in kWh')
@click.option('--source', default='solar-1', help='Energiequellen-ID')
def submit_energy(node, kwh, source):
    if node not in nodes:
        click.echo(f"❌ Node {node} nicht gefunden")
        return
    
    try:
        tx = nodes[node].submit_energy(kwh, source)
        click.echo(f"✅ Energie gemeldet")
        click.echo(f"   Menge: {kwh} kWh")
        click.echo(f"   Quelle: {source}")
        click.echo(f"   TX Hash: {tx.hash[:8]}...")
    except Exception as e:
        click.echo(f"❌ Fehler: {e}")


@cli.command()
def confirm():
    tips = list(tangle.tips)
    
    if len(tips) <= 1:
        click.echo("ℹ️  Keine Transactions zu bestätigen")
        return
    
    for tip in tips:
        if tip != tangle.GENESIS_HASH:
            tangle.confirmations[tip] += 1
    
    click.echo(f"✅ Confirmations hinzugefügt für {len(tips)} Transactions")
    
    newly_minted = token_engine.process_confirmed_transactions()
    if newly_minted:
        click.echo(f"\n💰 Tokens gemint:")
        for m in newly_minted:
            click.echo(f"   {m['node'][:8]}: +{m['tokens']} tokens ({m['kwh']} kWh)")


@cli.command()
def show_balances():
    balances = token_engine.get_all_balances()
    
    if not balances:
        click.echo("ℹ️  Keine Balances vorhanden")
        return
    
    click.echo("💰 Token-Balances:")
    for address, balance in balances.items():
        click.echo(f"   {address}: {balance} tokens")


@cli.command()
def show_tangle():
    stats = tangle.get_stats()
    token_stats = token_engine.get_stats()
    
    click.echo("\n📊 === Atlas MVP Statistiken ===\n")
    
    click.echo("Tangle:")
    click.echo(f"  Gesamt Transactions: {stats['total_transactions']}")
    click.echo(f"  Bestätigte: {stats['confirmed_transactions']}")
    click.echo(f"  Tips (unbestätigt): {stats['tips']}")
    click.echo(f"  Nodes: {stats['nodes']}")
    
    click.echo("\nToken System:")
    click.echo(f"  Geminte Transactions: {token_stats['total_minted_txs']}")
    click.echo(f"  Token-Holder: {token_stats['total_token_holders']}")
    click.echo(f"  Gesamt Supply: {token_stats['total_supply']} tokens")


@cli.command()
def list_nodes():
    if not nodes:
        click.echo("Keine Nodes erstellt")
        return
    
    click.echo("✅ Aktive Nodes:")
    for address in nodes.keys():
        click.echo(f"   {address}")


if __name__ == '__main__':
    cli()