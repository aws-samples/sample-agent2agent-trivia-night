"""
Adverse Event Signal Detection Agent

A single Strands agent for detecting safety signals in adverse event reports,
searching medical literature for evidence, and generating regulatory reports.
Deployed to Amazon Bedrock AgentCore Runtime as an A2A server.
"""

import os
import logging

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.types.content import SystemContentBlock
from strands_tools import editor

from ae_config import MODEL_ID, SYSTEM_PROMPT
from detect_signals import detect_signals_tool
from search_literature import search_literature_tool
from generate_report import generate_report_tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

system_content = [
    SystemContentBlock(text=SYSTEM_PROMPT),
    SystemContentBlock(cachePoint={"type": "default"}),
]

model = BedrockModel(
    model_id=MODEL_ID,
    max_tokens=10000,
    cache_tools="default",
    temperature=1,
    additional_request_fields={
        "anthropic_beta": ["interleaved-thinking-2025-05-14"],
        "reasoning_config": {
            "type": "enabled",
            "budget_tokens": 3000,
        },
    },
)

os.environ["BYPASS_TOOL_CONSENT"] = "true"

strands_agent = Agent(
    model=model,
    description=(
        "An adverse event signal detection agent that analyzes pharmacovigilance data, "
        "searches medical literature, and generates FDA/EMA regulatory reports."
    ),
    tools=[editor, detect_signals_tool, search_literature_tool, generate_report_tool],
    system_prompt=system_content,
)

### A2A Server ###
from strands.multiagent.a2a import A2AServer
import uvicorn
from fastapi import FastAPI

runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
logger.info(f"Runtime URL: {runtime_url}")
host, port = "0.0.0.0", 9000  # nosec B104

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
