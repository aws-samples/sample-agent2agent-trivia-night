import asyncio

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from search_pmc import search_pmc_tool
from gather_evidence import gather_evidence_tool
from strands import Agent
from strands.models import BedrockModel
from strands.types.content import SystemContentBlock
import logging
from strands_tools import editor
import os

from config import MODEL_ID, SYSTEM_PROMPT

app = BedrockAgentCoreApp()

# Define system content with cache points
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
    description="A deep research agent for generating technical surveys of life science topics based on research from PubMed Central.",
    tools=[editor, search_pmc_tool, gather_evidence_tool],
    system_prompt=system_content,
)

### A2A Server Content ###
#  
from strands.multiagent.a2a import A2AServer
import uvicorn
from fastapi import FastAPI
# Use the complete runtime URL from environment variable, fallback to local
runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
logging.info(f"Runtime URL: {runtime_url}")
host, port = "0.0.0.0", 9000  # nosec B104 — binds all interfaces intentionally; runs inside a container behind AgentCore Runtime proxy

# Pass runtime_url to http_url parameter AND use serve_at_root=True
a2a_server = A2AServer(
    agent=strands_agent,
    http_url=runtime_url,
    serve_at_root=True,  # Serves locally at root (/) regardless of remote URL path complexity
    enable_a2a_compliant_streaming=True
)

app = FastAPI()


@app.get("/ping")
def ping():
    return {"status": "healthy"}


# AgentCore Runtime proxies GET requests as POST, so handle both
@app.post("/.well-known/agent-card.json")
def agent_card_post():
    return a2a_server.public_agent_card


app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host=host, port=port)



# @app.entrypoint
# async def strands_agent_bedrock(payload):
#     """
#     Invoke the agent with a payload
#     """
#     user_input = payload.get("prompt")
#     print("User input:", user_input)
#     try:
#         async for event in strands_agent.stream_async(user_input):

#             # Print tool use
#             for content in event.get("message", {}).get("content", []):
#                 if tool_use := content.get("toolUse"):
#                     yield "\n"
#                     yield f"🔧 Using tool: {tool_use['name']}"
#                     for k, v in tool_use["input"].items():
#                         yield f"**{k}**: {v}\n"
#                     yield "\n"

#             # Print event data
#             if "data" in event:
#                 yield event["data"]
#     except Exception as e:
#         yield f"Error: {str(e)}"


# if __name__ == "__main__":
#     app.run()
