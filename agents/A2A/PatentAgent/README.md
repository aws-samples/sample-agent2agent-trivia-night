# USPTO Patent Agent

A patent research agent that searches USPTO Patent Public Search (ppubs.uspto.gov) for granted patents, published applications, and patent documents. No API key required.

Supports two modes:
- **Local terminal chat** via `agent_main.py`
- **A2A protocol server** via `main.py` for AgentCore Runtime deployment

## Tools

| Tool | Description |
|------|-------------|
| `ppubs_search_patents` | Search granted US patents (full-text) |
| `ppubs_search_applications` | Search published patent applications |
| `ppubs_get_patent_by_number` | Get patent full text by number |
| `ppubs_get_full_document` | Get complete document by GUID |
| `ppubs_download_patent_pdf` | Download patent as PDF |
| `get_cpc_info` | Look up CPC classification codes |
| `get_status_code` | Look up USPTO status code meaning |
| `check_api_status` | Check PPUBS API availability |

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- AWS CLI configured with Bedrock access (for A2A mode)

## Installation

```bash
cd patent_agent
uv sync
```

## Local Terminal Chat

```bash
uv run agent_main.py
```

Type `quit` or `Ctrl+C` to exit.

## Local A2A Server Testing

1. Start the server:
   ```bash
   uv run main.py
   ```

2. Verify the agent card:
   ```bash
   curl http://localhost:9000/.well-known/agent-card.json | jq .
   ```

3. Send a test message:
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
           "parts": [{"kind": "text", "text": "search for patents about machine learning"}],
           "messageId": "12345678-1234-1234-1234-123456789012"
         }
       }
     }' | jq .
   ```

## Deploy to AgentCore Runtime

1. Configure the agent:
   ```bash
   uv run agentcore configure -e main.py --protocol A2A
   ```

2. Deploy:
   ```bash
   uv run agentcore deploy
   ```

3. Set the agent ARN from the deploy output:
   ```bash
   export AGENT_ARN=<arn from deploy output>
   ```

4. Get an M2M token:
   ```bash
   uv run ../scripts/get_m2m_token.py
   export BEARER_TOKEN=<token from previous step>
   ```

5. Verify the deployed agent card:
   ```bash
   uv run ../scripts/get_agent_card.py
   ```
