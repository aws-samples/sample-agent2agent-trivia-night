# A2A Server Best Practices: Strands Agents + Amazon Bedrock AgentCore

## What is A2A?

The [Agent-to-Agent (A2A) protocol](https://a2aproject.github.io/A2A/latest/) is an open standard for agent discovery, communication, and collaboration across platforms. Agents expose themselves as HTTP servers speaking JSON-RPC 2.0, and publish an **Agent Card** at `/.well-known/agent-card.json` for discovery.

---

## Building an A2A Server with Strands

### Installation

```bash
pip install strands-agents[a2a] strands-agents-tools
```

### Minimal Server

```python
from strands import Agent
from strands.multiagent.a2a import A2AServer

agent = Agent(
    name="My Agent",
    description="What this agent does — used in the Agent Card.",
    tools=[...],
    callback_handler=None  # suppress streaming output noise
)

a2a_server = A2AServer(agent=agent)
a2a_server.serve()  # binds to 127.0.0.1:9000 by default
```

The server handles both `message/send` (sync) and `message/stream` (streaming) JSON-RPC methods automatically.

### Key `A2AServer` Options

| Option | Default | Notes |
|---|---|---|
| `host` | `127.0.0.1` | Bind address |
| `port` | `9000` | A2A standard port |
| `http_url` | `None` | Public URL — sets the Agent Card's `url` field |
| `serve_at_root` | `False` | Serve at `/` even when `http_url` has a path prefix (needed for AgentCore) |
| `skills` | auto | Auto-generated from tools; override for custom descriptions |
| `task_store` | `InMemoryTaskStore` | Swap for persistent storage in production |

### Mounting in FastAPI (for AgentCore)

When deploying to AgentCore, mount the A2A app at root and add a `/ping` health check:

```python
import os, uvicorn
from fastapi import FastAPI
from strands import Agent
from strands.multiagent.a2a import A2AServer

runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")

agent = Agent(name="My Agent", description="...", tools=[...], callback_handler=None)

a2a_server = A2AServer(agent=agent, http_url=runtime_url, serve_at_root=True)

app = FastAPI()

@app.get("/ping")
def ping():
    return {"status": "healthy"}

app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
```

`serve_at_root=True` is critical — AgentCore passes the full runtime URL as `http_url`, but the container must still serve at `/`.

---

## Deploying to Amazon Bedrock AgentCore Runtime

AgentCore acts as a transparent proxy for A2A, adding enterprise auth (SigV4 / OAuth 2.0) and session isolation without modifying JSON-RPC payloads.

### Protocol Differences vs. Other AgentCore Modes

| | A2A | HTTP | MCP |
|---|---|---|---|
| Port | `9000` | `8080` | `8000` |
| Mount path | `/` | `/invocations` | `/mcp` |
| Discovery | Agent Card at `/.well-known/agent-card.json` | — | — |
| Protocol | JSON-RPC 2.0 | HTTP | MCP |

### Deployment Steps

```bash
# 1. Install toolkit
pip install bedrock-agentcore-starter-toolkit

# 2. Configure (select A2A protocol)
agentcore configure -e my_a2a_server.py --protocol A2A

# 3. Deploy
agentcore deploy
# → returns an ARN: arn:aws:bedrock-agentcore:<region>:<account>:runtime/<name>
```

### Project Structure

```
your_project/
├── my_a2a_server.py    # agent + FastAPI app
└── requirements.txt    # strands-agents[a2a], bedrock-agentcore, strands-agents-tools
```

### Authentication

Configure a Cognito user pool during `agentcore configure`. Deployed servers require a Bearer token in the `Authorization` header plus `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` for session isolation.

### Retrieving the Agent Card (post-deploy)

```bash
curl -H "Authorization: Bearer $BEARER_TOKEN" \
     -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: <uuid>" \
     "https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<encoded-arn>/invocations/.well-known/agent-card.json"
```

The Agent Card's `url` field is the value to set as `AGENTCORE_RUNTIME_URL` in your server code.

---

## Consuming A2A Agents (Client Side)

### Using `A2AAgent` in Strands (simplest)

```python
from strands.multiagent.a2a import A2AAgent

remote = A2AAgent(agent_url="http://localhost:9000")
result = remote("What is 42 * 7?")
```

### Using as a Tool inside another Strands Agent

```python
from strands import Agent
from strands.multiagent.a2a import A2AAgent

calculator = A2AAgent(agent_url="http://localhost:9000")

orchestrator = Agent(
    name="Orchestrator",
    tools=[calculator.as_tool()]
)
```

---

## Key Best Practices

- **Agent Card quality matters** — the `name` and `description` on your `Agent` become the Agent Card metadata that other agents use for discovery and routing. Write them clearly.
- **Use `callback_handler=None`** on agents wrapped in `A2AServer` to avoid streaming output interfering with the JSON-RPC response.
- **Port 9000 is the A2A standard** — don't change it unless you have a specific reason.
- **`serve_at_root=True` is required for AgentCore** — AgentCore's runtime URL includes a path, but the container must serve at `/`.
- **Swap `InMemoryTaskStore` for production** — the default task store is in-memory and won't survive restarts. Implement `TaskStore` backed by DynamoDB or another persistent store for production workloads.
- **Error handling follows JSON-RPC** — A2A errors are returned as JSON-RPC error objects with HTTP 200. Don't rely on HTTP status codes for error detection in clients.
- **Test locally before deploying** — run `python my_a2a_server.py` and hit `http://localhost:9000/.well-known/agent-card.json` to validate the Agent Card before deploying to AgentCore.
