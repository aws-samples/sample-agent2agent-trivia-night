# ClinicalTrialsResearcher

An A2A-compliant research agent that searches clinical trials on ClinicalTrials.gov, queries FDA-approved drug information from OpenFDA, and creates data visualizations.

## Tools

| Tool | Description |
|------|-------------|
| `search_trials` | Search ClinicalTrials.gov for trials by condition, intervention, and filters |
| `get_trial_details` | Get detailed info for a specific trial by NCT ID |
| `get_approved_drugs` | Query OpenFDA for approved drugs by condition |
| `create_pie_chart` | Generate a pie chart, upload to S3, and return a presigned URL |

## Setup

```bash
cd agents/A2A/ClinicalTrialsResearcher
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Local Testing

Start the A2A server locally:

```bash
python main.py
```

The server runs on `http://0.0.0.0:9000`. Verify it's healthy:

```bash
curl http://localhost:9000/ping
# {"status":"healthy"}
```

Fetch the agent card:

```bash
curl http://localhost:9000/.well-known/agent-card.json
```

Send a message via A2A JSON-RPC:

```bash
curl -X POST http://localhost:9000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Find clinical trials for diabetes"}]
      }
    }
  }'
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENTCORE_RUNTIME_URL` | No | A2A server URL (default: `http://127.0.0.1:9000/`) |
| `CHART_IMAGE_BUCKET` | For charts | S3 bucket for uploading generated pie charts |

## Deploy to AgentCore

Follow the [AgentCore deployment guide](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-deploy.html) to deploy this agent. The agent listens on port 9000 and exposes `/ping` for health checks.

## Running Tests

```bash
pytest tests/ -v
```

## File Structure

```
ClinicalTrialsResearcher/
├── main.py                    # A2A server entry point
├── config.py                  # MODEL_ID + SYSTEM_PROMPT
├── clinical_trials_tools.py   # search_trials, get_trial_details
├── drug_info_tools.py         # get_approved_drugs
├── visualization_tools.py     # create_pie_chart
├── requirements.txt
├── README.md
├── agent_card.json            # Reference copy of agent card
└── tests/                     # Property-based tests
```
