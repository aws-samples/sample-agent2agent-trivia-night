import logging
import os

import uvicorn
from fastapi import FastAPI
from strands import Agent
from strands.models import BedrockModel
from strands.multiagent.a2a import A2AServer

from config import MODEL_ID, REGION, SYSTEM_PROMPT
from tools import statistician_tools

os.environ["BYPASS_TOOL_CONSENT"] = "true"

logging.basicConfig(level=logging.INFO)

model = BedrockModel(
    model_id=MODEL_ID,
    region_name=REGION,
    temperature=0.1,
)

strands_agent = Agent(
    name="Statistician Agent",
    description="A medical research assistant specialized in survival analysis with biomarkers. "
    "Can create Kaplan-Meier plots, fit Cox Proportional Hazards regression models, "
    "and generate statistical visualizations using clinical genomic data.",
    model=model,
    tools=statistician_tools,
    system_prompt=SYSTEM_PROMPT,
    callback_handler=None,
)

# ---------------------------------------------------------------------------
# A2A Server
# ---------------------------------------------------------------------------

runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
logging.info(f"Runtime URL: {runtime_url}")
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


# AgentCore Runtime proxies GET requests as POST, so handle both
@app.post("/.well-known/agent-card.json")
def agent_card_post():
    return a2a_server.public_agent_card


app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host=host, port=port)
