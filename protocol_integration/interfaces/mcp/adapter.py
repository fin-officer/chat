import asyncio
import json
import websockets
from typing import Dict, Any, List, Optional
import os
import logging

from protocol_integration.core.protocol import ProtocolRegistry
from protocol_integration.core.message import Message
from protocol_integration.llm.client import LLMClient

logger = logging.getLogger(__name__)

class MCPAdapter:
    def __init__(
        self, 
        llm_client: LLMClient, 
        protocol_registry: ProtocolRegistry,
        host: str = "0.0.0.0", 
        port: int = 8080
    ):
        self.llm_client = llm_client
        self.protocol_registry = protocol_registry
        self.host = host
        self.port = port
        self.connections = set()
        self.handlers = {
            "list_protocols": self.handle_list_protocols,
            "activate_protocol": self.handle_activate_protocol,
            "deactivate_protocol": self.handle_deactivate_protocol,
            "send_message": self.handle_send_message,
            "simulate_message": self.handle_simulate_message,
        }
    
    async def handle_list_protocols(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list_protocols request from MCP"""
        protocols = self.protocol_registry.list_protocols()
        result = []
        
        for name, protocol in protocols.items():
            status = "active" if protocol.is_running() else "inactive"
            config = protocol.get_config()
            result.append({
                "name": name,
                "status": status,
                "config": config
            })
        
        return {
            "protocols": result,
            "status": "success"
        }
    
    async def handle_activate_protocol(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle activate_protocol request from MCP"""
        protocol_name = data.get("protocol_name")
        if not protocol_name:
            return {"error": "Protocol name is required", "status": "error"}
        
        protocols = self.protocol_registry.list_protocols()
        
        if protocol_name not in protocols:
            return {"error": f"Protocol '{protocol_name}' not found", "status": "error"}
        
        protocol = protocols[protocol_name]
        
        if not protocol.is_running():
            await protocol.start()
        
        return {
            "protocol": {
                "name": protocol_name,
                "status": "active",
                "config": protocol.get_config()
            },
            "status": "success"
        }
    
    async def handle_deactivate_protocol(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle deactivate_protocol request from MCP"""
        protocol_name = data.get("protocol_name")
        if not protocol_name:
            return {"error": "Protocol name is required", "status": "error"}
        
        protocols = self.protocol_registry.list_protocols()
        
        if protocol_name not in protocols:
            return {"error": f"Protocol '{protocol_name}' not found", "status": "error"}
        
        protocol = protocols[protocol_name]
        
        if protocol.is_running():
            await protocol.stop()
        
        return {
            "protocol": {
                "name": protocol_name,
                "status": "inactive",
                "config": protocol.get_config()
            },
            "status": "success"
        }
    
    async def handle_send_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle send_message request from MCP"""
        content = data.get("content")
        protocol_name = data.get("protocol")
        recipient = data.get("recipient")
        metadata = data.get("metadata", {})
        
        if not content:
            return {"error": "Message content is required", "status": "error"}
        
        if not protocol_name:
            return {"error": "Protocol name is required", "status": "error"}
        
        protocols = self.protocol_registry.list_protocols()
        
        if protocol_name not in protocols:
            return {"error": f"Protocol '{protocol_name}' not found", "status": "error"}
        
        protocol = protocols[protocol_name]
        
        if not protocol.is_running():
            return {"error": f"Protocol '{protocol_name}' is not active", "status": "error"}
        
        message = Message(
            content=content,
            sender="mcp",
            protocol=protocol_name,
            recipient=recipient,
            metadata=metadata
        )
        
        try:
            message_id = protocol.generate_id()
            message.id = message_id
            
            # Send message asynchronously
            asyncio.create_task(protocol.send_message(message))
            
            return {
                "message_id": message_id,
                "status": "queued"
            }
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {"error": str(e), "status": "error"}
    
    async def handle_simulate_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle simulate_message request from MCP"""
        content = data.get("content")
        protocol_name = data.get("protocol")
        metadata = data.get("metadata", {})
        
        if not content:
            return {"error": "Message content is required", "status": "error"}
        
        if not protocol_name:
            return {"error": "Protocol name is required", "status": "error"}
        
        protocols = self.protocol_registry.list_protocols()
        
        if protocol_name not in protocols:
            return {"error": f"Protocol '{protocol_name}' not found", "status": "error"}
        
        protocol = protocols[protocol_name]
        
        message = Message(
            content=content,
            sender="external",
            protocol=protocol_name,
            recipient="system",
            metadata=metadata
        )
        
        try:
            # Process message with LLM
            llm_response = self.llm_client.generate(content)
            
            response_message = Message(
                content=llm_response.text,
                sender="llm",
                protocol=protocol_name,
                recipient=message.sender,
                metadata={"in_response_to": message.id}
            )
            
            return {
                "original_message": message.dict(),
                "llm_response": response_message.dict(),
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error simulating message: {e}")
            return {"error": str(e), "status": "error"}
    
    async def handle_message(self, websocket, message: str):
        """Handle incoming MCP message"""
        try:
            data = json.loads(message)
            action = data.get("action")
            
            if action in self.handlers:
                result = await self.handlers[action](data)
                await websocket.send(json.dumps({
                    "id": data.get("id"),
                    "result": result
                }))
            else:
                await websocket.send(json.dumps({
                    "id": data.get("id"),
                    "error": f"Unknown action: {action}"
                }))
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "error": "Invalid JSON"
            }))
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await websocket.send(json.dumps({
                "error": str(e)
            }))
    
    async def handler(self, websocket, path):
        """WebSocket connection handler"""
        self.connections.add(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        finally:
            self.connections.remove(websocket)
    
    async def run(self):
        """Run the MCP adapter server"""
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # Run forever

def start():
    """Start the MCP adapter"""
    # Initialize LLM client
    llm_host = os.environ.get("LLM_HOST", "http://localhost:11434")
    llm_client = LLMClient(host=llm_host)
    
    # Initialize protocol registry
    from protocol_integration.protocols.chat import ChatProtocol
    from protocol_integration.protocols.email import EmailProtocol
    from protocol_integration.protocols.discord import DiscordProtocol
    from protocol_integration.protocols.slack import SlackProtocol
    
    protocol_registry = ProtocolRegistry()
    
    # Register protocols based on environment configuration
    if os.environ.get("ENABLE_CHAT", "true").lower() == "true":
        protocol_registry.register("chat", ChatProtocol(llm_client))
    
    if os.environ.get("ENABLE_EMAIL", "false").lower() == "true":
        email_config = {
            "host": os.environ.get("EMAIL_HOST"),
            "user": os.environ.get("EMAIL_USER"),
            "password": os.environ.get("EMAIL_PASSWORD")
        }
        protocol_registry.register("email", EmailProtocol(llm_client, **email_config))
    
    if os.environ.get("ENABLE_DISCORD", "false").lower() == "true":
        discord_config = {
            "token": os.environ.get("DISCORD_TOKEN")
        }
        protocol_registry.register("discord", DiscordProtocol(llm_client, **discord_config))
    
    if os.environ.get("ENABLE_SLACK", "false").lower() == "true":
        slack_config = {
            "token": os.environ.get("SLACK_TOKEN")
        }
        protocol_registry.register("slack", SlackProtocol(llm_client, **slack_config))
    
    # Start protocols that should be auto-started
    for name, protocol in protocol_registry.list_protocols().items():
        if os.environ.get(f"AUTOSTART_{name.upper()}", "false").lower() == "true":
            asyncio.run(protocol.start())
    
    # Start MCP adapter
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", 8080))
    
    adapter = MCPAdapter(
        llm_client=llm_client,
        protocol_registry=protocol_registry,
        host=host,
        port=port
    )
    
    asyncio.run(adapter.run())

if __name__ == "__main__":
    start()