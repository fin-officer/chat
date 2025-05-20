from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
import os
import asyncio

from protocol_integration.core.protocol import ProtocolRegistry
from protocol_integration.core.message import Message
from protocol_integration.llm.client import LLMClient
from protocol_integration.protocols.chat import ChatProtocol
from protocol_integration.protocols.email import EmailProtocol
from protocol_integration.protocols.discord import DiscordProtocol
from protocol_integration.protocols.slack import SlackProtocol

app = FastAPI(
    title="Protocol Integration API",
    description="REST API for Protocol Integration with LLM",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize global registry and LLM client
llm_client = None
protocol_registry = None

class ProtocolStatus(BaseModel):
    name: str
    status: str
    config: Dict[str, Any] = {}

class MessageRequest(BaseModel):
    content: str
    protocol: str
    recipient: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class MessageResponse(BaseModel):
    id: str
    status: str
    message: Optional[str] = None

# Dependency
def get_registry():
    return protocol_registry

@app.on_event("startup")
async def startup_event():
    global llm_client, protocol_registry
    
    # Initialize LLM client
    llm_host = os.environ.get("LLM_HOST", "http://localhost:11434")
    llm_client = LLMClient(host=llm_host)
    
    # Initialize protocol registry
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
            await protocol.start()

@app.on_event("shutdown")
async def shutdown_event():
    if protocol_registry:
        for name, protocol in protocol_registry.list_protocols().items():
            if protocol.is_running():
                await protocol.stop()

@app.get("/health", summary="Health check endpoint")
async def health_check():
    """Check if the API is running"""
    return {"status": "ok"}

@app.get("/protocols", response_model=List[ProtocolStatus], summary="List available protocols")
async def list_protocols(registry: ProtocolRegistry = Depends(get_registry)):
    """List all available protocols and their status"""
    protocols = registry.list_protocols()
    result = []
    
    for name, protocol in protocols.items():
        status = "active" if protocol.is_running() else "inactive"
        config = protocol.get_config()
        result.append(ProtocolStatus(name=name, status=status, config=config))
    
    return result

@app.post("/protocols/{protocol_name}/activate", response_model=ProtocolStatus, summary="Activate a protocol")
async def activate_protocol(
    protocol_name: str,
    registry: ProtocolRegistry = Depends(get_registry)
):
    """Activate a specific protocol"""
    protocols = registry.list_protocols()
    
    if protocol_name not in protocols:
        raise HTTPException(status_code=404, detail=f"Protocol '{protocol_name}' not found")
    
    protocol = protocols[protocol_name]
    
    if not protocol.is_running():
        await protocol.start()
    
    return ProtocolStatus(
        name=protocol_name,
        status="active",
        config=protocol.get_config()
    )

@app.post("/protocols/{protocol_name}/deactivate", response_model=ProtocolStatus, summary="Deactivate a protocol")
async def deactivate_protocol(
    protocol_name: str,
    registry: ProtocolRegistry = Depends(get_registry)
):
    """Deactivate a specific protocol"""
    protocols = registry.list_protocols()


@app.post("/send", response_model=MessageResponse, summary="Send a message")
async def send_message(
        request: MessageRequest,
        background_tasks: BackgroundTasks,
        registry: ProtocolRegistry = Depends(get_registry)
):
    """Send a message through a specific protocol"""
    protocols = registry.list_protocols()

    if request.protocol not in protocols:
        raise HTTPException(status_code=404, detail=f"Protocol '{request.protocol}' not found")

    protocol = protocols[request.protocol]

    if not protocol.is_running():
        raise HTTPException(status_code=400, detail=f"Protocol '{request.protocol}' is not active")

    message = Message(
        content=request.content,
        sender="api",
        protocol=request.protocol,
        recipient=request.recipient,
        metadata=request.metadata
    )

    try:
        # Send message asynchronously
        message_id = protocol.generate_id()
        background_tasks.add_task(protocol.send_message, message)

        return MessageResponse(
            id=message_id,
            status="queued",
            message="Message queued for delivery"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/simulate", response_model=Dict[str, Any], summary="Simulate receiving a message")
async def simulate_message(
        request: MessageRequest,
        registry: ProtocolRegistry = Depends(get_registry)
):
    """Simulate receiving a message through a specific protocol"""
    protocols = registry.list_protocols()

    if request.protocol not in protocols:
        raise HTTPException(status_code=404, detail=f"Protocol '{request.protocol}' not found")

    protocol = protocols[request.protocol]

    message = Message(
        content=request.content,
        sender="external",
        protocol=request.protocol,
        recipient="system",
        metadata=request.metadata
    )

    try:
        # Process message with LLM
        llm_response = llm_client.generate(request.content)

        response_message = Message(
            content=llm_response.text,
            sender="llm",
            protocol=request.protocol,
            recipient=message.sender,
            metadata={"in_response_to": message.id}
        )

        return {
            "original_message": message.dict(),
            "llm_response": response_message.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def start():
    """Start the FastAPI server"""
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("protocol_integration.interfaces.rest.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    start()