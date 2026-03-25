import os
import uvicorn
from fastapi import FastAPI
from strands import Agent
from strands.multiagent.a2a import A2AServer

from config import MODEL_ID, SYSTEM_PROMPT
from clinical_trials_tools import search_trials, get_trial_details
from drug_info_tools import get_approved_drugs
from visualization_tools import create_pie_chart

# Create unified agent with all tools
strands_agent = Agent(
    name="ClinicalTrialsResearcher",
    description="A research agent that searches clinical trials on ClinicalTrials.gov, queries FDA-approved drug information from OpenFDA, and creates data visualizations like pie charts.",
    model=MODEL_ID,
    system_prompt=SYSTEM_PROMPT,
    tools=[search_trials, get_trial_details, get_approved_drugs, create_pie_chart],
    callback_handler=None,
)

# A2A server setup
runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
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
    host, port = "0.0.0.0", 9000
    uvicorn.run(app, host=host, port=port)
