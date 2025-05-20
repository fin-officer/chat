#!/usr/bin/env python
import cmd
import typer
import asyncio
from rich.console import Console
from rich.table import Table
from typing import List, Optional

from protocol_integration.core.protocol import ProtocolRegistry
from protocol_integration.core.message import Message
from protocol_integration.llm.client import LLMClient

console = Console()
app = typer.Typer()

class ProtocolShell(cmd.Cmd):
    intro = "Welcome to Protocol Integration Shell. Type help or ? to list commands."
    prompt = "protocol> "
    
    def __init__(self, llm_client: LLMClient, protocol_registry: ProtocolRegistry):
        super().__init__()
        self.llm_client = llm_client
        self.protocol_registry = protocol_registry
        self.active_protocol = None
    
    def do_protocols(self, arg):
        """List available protocols"""
        protocols = self.protocol_registry.list_protocols()
        
        if not protocols:
            console.print("[yellow]No protocols registered[/yellow]")
            return
        
        table = Table(title="Available Protocols")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        
        for name, protocol in protocols.items():
            status = "Active" if protocol.is_running() else "Inactive"
            table.add_row(name, status)
        
        console.print(table)
    
    def do_activate(self, arg):
        """Activate a protocol: activate [protocol_name]"""
        if not arg:
            console.print("[yellow]Please provide a protocol name[/yellow]")
            return
        
        protocols = self.protocol_registry.list_protocols()
        if arg not in protocols:
            console.print(f"[red]Protocol '{arg}' not found[/red]")
            return
        
        protocol = protocols[arg]
        if not protocol.is_running():
            asyncio.run(protocol.start())
            console.print(f"[green]Protocol '{arg}' activated[/green]")
        else:
            console.print(f"[yellow]Protocol '{arg}' is already active[/yellow]")
        
        self.active_protocol = arg
    
    def do_deactivate(self, arg):
        """Deactivate a protocol: deactivate [protocol_name]"""
        if not arg:
            console.print("[yellow]Please provide a protocol name[/yellow]")
            return
        
        protocols = self.protocol_registry.list_protocols()
        if arg not in protocols:
            console.print(f"[red]Protocol '{arg}' not found[/red]")
            return
        
        protocol = protocols[arg]
        if protocol.is_running():
            asyncio.run(protocol.stop())
            console.print(f"[green]Protocol '{arg}' deactivated[/green]")
        else:
            console.print(f"[yellow]Protocol '{arg}' is already inactive[/yellow]")
        
        if self.active_protocol == arg:
            self.active_protocol = None
    
    def do_send(self, arg):
        """Send a message through the active protocol: send [message]"""
        if not self.active_protocol:
            console.print("[yellow]No active protocol. Please activate one first.[/yellow]")
            return
        
        if not arg:
            console.print("[yellow]Please provide a message[/yellow]")
            return
        
        protocols = self.protocol_registry.list_protocols()
        protocol = protocols[self.active_protocol]
        
        message = Message(
            content=arg,
            sender="user",
            protocol=self.active_protocol
        )
        
        try:
            asyncio.run(protocol.send_message(message))
            console.print(f"[green]Message sent through '{self.active_protocol}'[/green]")
        except Exception as e:
            console.print(f"[red]Error sending message: {e}[/red]")
    
    def do_simulate(self, arg):
        """Simulate receiving a message: simulate [message]"""
        if not self.active_protocol:
            console.print("[yellow]No active protocol. Please activate one first.[/yellow]")
            return
        
        if not arg:
            console.print("[yellow]Please provide a message[/yellow]")
            return
        
        protocols = self.protocol_registry.list_protocols()
        protocol = protocols[self.active_protocol]
        
        message = Message(
            content=arg,
            sender="external",
            protocol=self.active_protocol
        )
        
        try:
            # Process message with LLM and get response
            llm_response = self.llm_client.generate(arg)
            response_message = Message(
                content=llm_response.text,
                sender="llm",
                protocol=self.active_protocol
            )
            
            console.print(f"[blue]Simulated incoming message: {arg}[/blue]")
            console.print(f"[green]LLM response: {llm_response.text}[/green]")
        except Exception as e:
            console.print(f"[red]Error simulating message: {e}[/red]")
    
    def do_exit(self, arg):
        """Exit the shell"""
        return True
    
    # Aliases
    do_quit = do_exit
    do_list = do_protocols

@app.command()
def main(llm_host: str = "http://localhost:11434"):
    """Interactive Protocol Integration Shell"""
    from protocol_integration.llm.client import LLMClient
    from protocol_integration.core.protocol import ProtocolRegistry
    from protocol_integration.protocols.chat import ChatProtocol
    from protocol_integration.protocols.email import EmailProtocol
    
    # Initialize LLM client
    llm_client = LLMClient(host=llm_host)
    
    # Initialize protocol registry
    registry = ProtocolRegistry()
    
    # Register available protocols
    registry.register("chat", ChatProtocol(llm_client))
    registry.register("email", EmailProtocol(llm_client))
    
    # Create and run shell
    shell = ProtocolShell(llm_client, registry)
    shell.cmdloop()

if __name__ == "__main__":
    app()