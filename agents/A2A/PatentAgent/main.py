import os
import logging

from strands import Agent
from strands.models import BedrockModel
from strands.multiagent.a2a import A2AServer
from fastapi import FastAPI
import uvicorn

from tools import ALL_TOOLS

MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")

SYSTEM_PROMPT = """You are a USPTO patent research assistant. You have access to Patent Public Search
(ppubs.uspto.gov) tools for searching patents, applications, and downloading documents.
Help users find and analyze patent information."""

model = BedrockModel(model_id=MODEL_ID, max_tokens=4096)

strands_agent = Agent(
    name="Patent Agent",
    model=model,
    description="A patent research agent that searches USPTO Patent Public Search (ppubs.uspto.gov) for granted patents, published applications, and patent documents.",
    tools=ALL_TOOLS,
    system_prompt=SYSTEM_PROMPT,
)

# A2A server
runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
logging.info(f"Runtime URL: {runtime_url}")
host, port = "0.0.0.0", 9000  # nosec B104 — binds all interfaces; runs inside container behind AgentCore Runtime proxy

a2a_server = A2AServer(
    agent=strands_agent,
    http_url=runtime_url,
    serve_at_root=True,
    enable_a2a_compliant_streaming=True,
)

app = FastAPI()


@app.get("/ping")
def ping():
    return {"status": "healthy"}


@app.post("/.well-known/agent-card.json")
def agent_card_post():
    return a2a_server.public_agent_card


app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host=host, port=port)
