# arXiv Research Agent (A2A)

A research agent that searches and analyzes papers from arXiv, exposed as an A2A server. Specializes in computational and quantitative research relevant to life sciences.

## Tools

| Tool | Description |
|---|---|
| `search_arxiv_tool` | Full-text search across arXiv with category filtering and sorting |
| `get_paper_tool` | Retrieve full details for a specific paper by arXiv ID |

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
          "text": "Find recent papers on protein structure prediction with deep learning"
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
