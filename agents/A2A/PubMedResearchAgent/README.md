# PubMed Deep Research Agent

A Strands-based deep research agent for life sciences deployed to Amazon Bedrock AgentCore Runtime.

## Introduction

Artificial intelligence offers transformative opportunities to accelerate scientific research across multiple domains. AI can:

- Enhance scientific comprehension by understanding complex tables, figures, and text
- Support discovery through hypothesis generation and experimental planning
- Assist with drafting and revising manuscripts
- Facilitate peer review processes¹

Among these capabilities, the "survey" function—finding related work and generating comprehensive summary reports—represents a critical bottleneck in research workflows that AI agents can effectively address¹.

Deep research agents represent a specialized class of AI systems designed to autonomously conduct complex research tasks by planning research strategies, gathering information from diverse sources, analyzing findings, and synthesizing comprehensive reports with proper citations. Unlike general AI assistants that simply answer questions or single-function research tools that address isolated tasks, deep research agents provide end-to-end research orchestration with autonomous workflow capabilities, specialized research tools, and integrated reasoning across multiple research functions². These systems can conduct multi-step research that accomplishes in minutes what would take researchers many hours, leveraging advanced planning methodologies and sophisticated tool integration frameworks to handle complex tasks requiring multi-step reasoning³.

For scientific literature survey tasks, deep research agents excel because they can maintain context across multiple research phases, adapt their search strategies based on discovered information, and synthesize findings from hundreds of sources into coherent, well-cited reports. Their ability to autonomously plan research approaches, interact with domain-specific databases like PubMed Central, and apply advanced retrieval augmented generation techniques makes them particularly well-suited for navigating the vast and rapidly expanding scientific literature landscape.

Sources

1. Chen, Qiguang, et al. "AI4Research: A Survey of Artificial Intelligence for Scientific Research." arXiv, 5 Aug. 2025, doi.org/10.48550/arXiv.2507.01903 .
1. Xu, Renjun, and Jingwen Peng. "A Comprehensive Survey of Deep Research: Systems, Methodologies, and Applications." arXiv, 14 June 2025, doi:10.48550/arXiv.2506.12594 .
1. Engineering at Anthropic: How we built our multi-agent research system

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS CLI configured with appropriate credentials
- Access to Amazon Bedrock AgentCore

## Testing

1. uv add -r requirements.txt
2. uv run main.py
3. In a seperate terminal session run `curl http://localhost:9000/.well-known/agent-card.json | jq .` to get the agent card.
4. Next, run the following command to test the agent invokation.

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
          "text": "what are recent advances in GLP-1 drugs?"
        }
      ],
      "messageId": "12345678-1234-1234-1234-123456789012"
    }
  }
}' | jq .
```

## Deployment

1. Run `uv run agentcore configure -e main.py --protocol A2A` and configure the authorizer, memory, and other settings.
2. run `uv run agentcore deploy` to upload the agent code and deploy to AgentCore Runtime.
3. Run `export AGENT_ARN=<Access Token Value from previous step>`
4. Run `uv run ../../../scripts/get_m2m_token.py`
5. Run `export BEARER_TOKEN=<Access Token Value from previous step>`
6. Run `uv run ../../../scripts/get_agent_card.py`

