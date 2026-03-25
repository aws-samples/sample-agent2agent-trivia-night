# Adverse Event Signal Detection Agent

A Strands-based pharmacovigilance agent for detecting safety signals in adverse event reports, deployed to Amazon Bedrock AgentCore Runtime.

## Overview

Single agent with three integrated tools:
- `detect_signals_tool` — Statistical signal detection using PRR, ROR, IC025
- `search_literature_tool` — PubMed Central literature search for evidence
- `generate_report_tool` — FDA MedWatch and EMA EudraVigilance report generation

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS CLI configured with appropriate credentials
- Access to Amazon Bedrock AgentCore

## Testing

1. `uv add -r requirements.txt`
2. `uv run main.py`
3. Test the agent card: `curl http://localhost:9000/.well-known/agent-card.json | jq .`
4. Test invocation:

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
          "text": "Analyze these adverse events for safety signals: [{\"event_id\":\"E1\",\"drug_name\":\"DrugA\",\"adverse_event_term\":\"Headache\",\"medra_code\":\"10019211\",\"event_date\":\"2025-01-15\",\"outcome\":\"recovered\",\"reporter_type\":\"physician\"},{\"event_id\":\"E2\",\"drug_name\":\"DrugA\",\"adverse_event_term\":\"Headache\",\"medra_code\":\"10019211\",\"event_date\":\"2025-02-10\",\"outcome\":\"recovered\",\"reporter_type\":\"consumer\"},{\"event_id\":\"E3\",\"drug_name\":\"DrugB\",\"adverse_event_term\":\"Nausea\",\"medra_code\":\"10028813\",\"event_date\":\"2025-01-20\",\"outcome\":\"recovered\",\"reporter_type\":\"physician\"}]"
        }
      ],
      "messageId": "12345678-1234-1234-1234-123456789012"
    }
  }
}' | jq .
```

## Deployment

1. Run `uv run agentcore configure -e main.py --protocol A2A`
2. Run `uv run agentcore deploy`
