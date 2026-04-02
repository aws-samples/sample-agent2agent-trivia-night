# Statistician Agent (A2A)

Medical research assistant specialized in survival analysis with biomarkers, exposed as an A2A server.

## Tools

| Tool | Description |
|---|---|
| `run_code` | Execute arbitrary Python in a CodeInterpreter sandbox (matplotlib, pandas, lifelines, etc.) |
| `plot_kaplan_meier` | Generate Kaplan-Meier survival plots comparing two patient groups |
| `fit_survival_regression` | Fit a Cox Proportional Hazards model from clinical genomic data in S3 |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AWS_REGION` | Yes | AWS region for Bedrock and S3 |
| `AGENT_ASSET_BUCKET` | Yes | S3 bucket for storing charts and reading data |
| `STATISTICIAN_EXECUTION_ROLE_ARN` | Yes* | IAM role for CodeInterpreter (*or provide `utils.boto3_helper`) |
| `AGENTCORE_RUNTIME_URL` | No | Set by AgentCore at deploy time; defaults to `http://127.0.0.1:9000/` |

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS CLI configured with appropriate credentials
- Access to Amazon Bedrock AgentCore

## Testing

1. `uv add -r requirements.txt`
2. `uv run main.py`
3. In a separate terminal, check the agent card:

```bash
curl http://localhost:9000/.well-known/agent-card.json | jq .
```

4. Send a test message:

```bash
curl -X POST http://localhost:9000/ \
-H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "Create a bar chart for the top 5 gene biomarkers (TP53, BRCA1, EGFR, KRAS, MYC) with -log10(p-value) values: 8.3, 6.7, 5.9, 4.2, 3.8"
        }
      ],
      "messageId": "12345678-1234-1234-1234-123456789012"
    }
  }
}' | jq .
```

## Deployment

1. Run `uv run agentcore configure -e main.py --protocol A2A` and configure the authorizer, memory, and other settings.
2. Run `uv run agentcore deploy` to upload the agent code and deploy to AgentCore Runtime.

## Origin

Ported from the [cancer biomarker discovery notebook](https://github.com/aws-samples/amazon-bedrock-agents-healthcare-lifesciences/blob/main/multi_agent_collaboration/cancer_biomarker_discovery/strands_agentcore/04-statistician_strands_notebook.ipynb) in `amazon-bedrock-agents-healthcare-lifesciences`.
