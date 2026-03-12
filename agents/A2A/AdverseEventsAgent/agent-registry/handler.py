"""
A2A Agent Registry — Lambda Handler

Single Lambda function handling CRUD, semantic search, and health heartbeats
for AgentCard entries. Uses DynamoDB for storage, Bedrock Titan Embed V2 for
embeddings, and S3 Vectors for similarity search.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# AWS clients & config
# ---------------------------------------------------------------------------
TABLE_NAME = os.environ.get("TABLE_NAME", "A2AAgentRegistry")
S3V_BUCKET = os.environ.get("S3_VECTORS_BUCKET", "")
S3V_INDEX = os.environ.get("S3_VECTORS_INDEX", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
s3vectors = boto3.client("s3vectors", region_name=REGION)

EMBED_MODEL = "amazon.titan-embed-text-v2:0"
REQUIRED_FIELDS = ["name", "description", "url", "version", "skills"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def response(status_code, body):
    """Format an API Gateway proxy response with JSON body."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
        "body": json.dumps(body, default=str),
    }


def validate_agent_card(body):
    """Validate required AgentCard fields. Returns error string or None."""
    if not isinstance(body, dict):
        return "Body must be a JSON object"
    for field in REQUIRED_FIELDS:
        if field not in body:
            return f"Missing required field: {field}"
    if not isinstance(body["name"], str) or not body["name"].strip():
        return "name must be a non-empty string"
    if len(body["name"]) > 256:
        return "name must be 256 characters or fewer"
    if not isinstance(body["description"], str) or not body["description"].strip():
        return "description must be a non-empty string"
    if len(body["description"]) > 2048:
        return "description must be 2048 characters or fewer"
    if not isinstance(body["url"], str) or not body["url"].strip():
        return "url must be a non-empty string"
    if not isinstance(body["version"], str) or not body["version"].strip():
        return "version must be a non-empty string"
    if not isinstance(body["skills"], list):
        return "skills must be a list"
    for i, skill in enumerate(body["skills"]):
        if not isinstance(skill, dict) or "name" not in skill:
            return f"skills[{i}] must be an object with a 'name' field"
    return None


def embed_text(text):
    """Call Bedrock Titan Embed V2 and return a 1024-dim vector."""
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text}),
    )
    result = json.loads(resp["body"].read())
    return result["embedding"]


def extract_agent_id(path):
    """Extract agent_id from /agents/{id} or /agents/{id}/health."""
    parts = path.strip("/").split("/")
    # Expected: ["agents", "{id}"] or ["agents", "{id}", "health"]
    if len(parts) >= 2:
        return parts[1]
    return None


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------
def create_agent(event):
    """POST /agents — register a new agent."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return response(400, {"error": "Invalid JSON body"})

    err = validate_agent_card(body)
    if err:
        return response(400, {"error": f"Validation error: {err}"})

    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "agent_id": agent_id,
        "name": body["name"],
        "description": body["description"],
        "url": body["url"],
        "version": body["version"],
        "skills": body["skills"],
        "created_at": now,
        "updated_at": now,
        "status": "active",
    }

    try:
        table.put_item(Item=item)
    except ClientError as exc:
        print(f"DynamoDB put_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    try:
        embedding = embed_text(f"{body['name']}: {body['description']}")
    except ClientError as exc:
        print(f"Bedrock embed error: {exc}")
        return response(502, {"error": "Embedding service unavailable"})

    try:
        skill_names = [s["name"] for s in body["skills"]]
        s3vectors.put_vectors(
            vectorBucketName=S3V_BUCKET,
            indexName=S3V_INDEX,
            vectors=[
                {
                    "key": agent_id,
                    "data": {"float32": embedding},
                    "metadata": {"agent_id": agent_id, "skills": skill_names},
                }
            ],
        )
    except ClientError as exc:
        print(f"S3 Vectors put error: {exc}")
        return response(500, {"error": "Internal server error"})

    return response(201, {"agent_id": agent_id})


def get_agent(event):
    """GET /agents/{id} — retrieve a single agent."""
    agent_id = extract_agent_id(event["rawPath"])
    try:
        result = table.get_item(Key={"agent_id": agent_id})
    except ClientError as exc:
        print(f"DynamoDB get_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    item = result.get("Item")
    if not item:
        return response(404, {"error": f"Agent {agent_id} not found"})
    return response(200, item)


def list_agents():
    """GET /agents — return all registered agents."""
    try:
        result = table.scan()
        items = result.get("Items", [])
    except ClientError as exc:
        print(f"DynamoDB scan error: {exc}")
        return response(500, {"error": "Internal server error"})
    return response(200, {"agents": items})


def update_agent(event):
    """PUT /agents/{id} — update an existing agent."""
    agent_id = extract_agent_id(event["rawPath"])

    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return response(400, {"error": "Invalid JSON body"})

    err = validate_agent_card(body)
    if err:
        return response(400, {"error": f"Validation error: {err}"})

    # Check agent exists
    try:
        existing = table.get_item(Key={"agent_id": agent_id})
    except ClientError as exc:
        print(f"DynamoDB get_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    if "Item" not in existing:
        return response(404, {"error": f"Agent {agent_id} not found"})

    now = datetime.now(timezone.utc).isoformat()

    try:
        table.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET #n = :n, description = :d, #u = :url, version = :v, skills = :s, updated_at = :ua",
            ExpressionAttributeNames={"#n": "name", "#u": "url"},
            ExpressionAttributeValues={
                ":n": body["name"],
                ":d": body["description"],
                ":url": body["url"],
                ":v": body["version"],
                ":s": body["skills"],
                ":ua": now,
            },
        )
    except ClientError as exc:
        print(f"DynamoDB update_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    # Re-embed and replace vector
    try:
        embedding = embed_text(f"{body['name']}: {body['description']}")
    except ClientError as exc:
        print(f"Bedrock embed error: {exc}")
        return response(502, {"error": "Embedding service unavailable"})

    try:
        skill_names = [s["name"] for s in body["skills"]]
        # Delete old vector then put new one
        s3vectors.delete_vectors(
            vectorBucketName=S3V_BUCKET,
            indexName=S3V_INDEX,
            keys=[agent_id],
        )
        s3vectors.put_vectors(
            vectorBucketName=S3V_BUCKET,
            indexName=S3V_INDEX,
            vectors=[
                {
                    "key": agent_id,
                    "data": {"float32": embedding},
                    "metadata": {"agent_id": agent_id, "skills": skill_names},
                }
            ],
        )
    except ClientError as exc:
        print(f"S3 Vectors update error: {exc}")
        return response(500, {"error": "Internal server error"})

    return response(200, {"message": f"Agent {agent_id} updated"})


def delete_agent(event):
    """DELETE /agents/{id} — remove an agent."""
    agent_id = extract_agent_id(event["rawPath"])

    # Check agent exists
    try:
        existing = table.get_item(Key={"agent_id": agent_id})
    except ClientError as exc:
        print(f"DynamoDB get_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    if "Item" not in existing:
        return response(404, {"error": f"Agent {agent_id} not found"})

    try:
        table.delete_item(Key={"agent_id": agent_id})
    except ClientError as exc:
        print(f"DynamoDB delete_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    try:
        s3vectors.delete_vectors(
            vectorBucketName=S3V_BUCKET,
            indexName=S3V_INDEX,
            keys=[agent_id],
        )
    except ClientError as exc:
        print(f"S3 Vectors delete error: {exc}")
        return response(500, {"error": "Internal server error"})

    return response(200, {"message": f"Agent {agent_id} deleted"})


def search_agents(event):
    """GET /agents/search?query=...&skills=...&top_k=5 — semantic search."""
    params = event.get("queryStringParameters") or {}
    query = params.get("query", "").strip()

    if not query:
        return response(400, {"error": "query parameter is required"})

    top_k = int(params.get("top_k", "5"))
    skills_filter = params.get("skills", "")

    # Embed the query
    try:
        query_embedding = embed_text(query)
    except ClientError as exc:
        print(f"Bedrock embed error: {exc}")
        return response(502, {"error": "Embedding service unavailable"})

    # Build S3 Vectors query
    query_params = {
        "vectorBucketName": S3V_BUCKET,
        "indexName": S3V_INDEX,
        "queryVector": {"float32": query_embedding},
        "topK": top_k,
        "returnDistance": True,
        "returnMetadata": True,
    }

    if skills_filter:
        skill_list = [s.strip() for s in skills_filter.split(",") if s.strip()]
        if skill_list:
            # Filter: at least one skill matches (using $or + $eq on list metadata)
            query_params["filter"] = {
                "$or": [
                    {"skills": {"$eq": skill}}
                    for skill in skill_list
                ]
            }

    try:
        vector_results = s3vectors.query_vectors(**query_params)
    except ClientError as exc:
        print(f"S3 Vectors query error: {exc}")
        return response(500, {"error": "Internal server error"})

    # Fetch matched agents from DynamoDB
    results = []
    for vec in vector_results.get("vectors", []):
        agent_id = vec["key"]
        score = vec.get("distance", 0.0)
        try:
            item_resp = table.get_item(Key={"agent_id": agent_id})
            item = item_resp.get("Item")
            if item:
                item["similarity_score"] = score
                results.append(item)
        except ClientError:
            continue  # skip agents we can't fetch

    return response(200, {"results": results})


def health_heartbeat(event):
    """POST /agents/{id}/health — update heartbeat timestamp."""
    agent_id = extract_agent_id(event["rawPath"])

    # Check agent exists
    try:
        existing = table.get_item(Key={"agent_id": agent_id})
    except ClientError as exc:
        print(f"DynamoDB get_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    if "Item" not in existing:
        return response(404, {"error": f"Agent {agent_id} not found"})

    now = datetime.now(timezone.utc).isoformat()

    # Parse optional status from body
    status = "active"
    try:
        body = json.loads(event.get("body", "{}") or "{}")
        status = body.get("status", "active")
    except (json.JSONDecodeError, TypeError):
        pass  # use default status

    try:
        table.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET last_heartbeat = :hb, #st = :s",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":hb": now, ":s": status},
        )
    except ClientError as exc:
        print(f"DynamoDB update_item error: {exc}")
        return response(500, {"error": "Internal server error"})

    return response(200, {"message": f"Heartbeat recorded for agent {agent_id}"})


# ---------------------------------------------------------------------------
# Main handler — route dispatch
# ---------------------------------------------------------------------------
def handler(event, context):
    """Lambda entry point. Dispatches to route handlers based on method + path."""
    try:
        method = event["requestContext"]["http"]["method"]
        path = event["rawPath"]
    except (KeyError, TypeError):
        return response(400, {"error": "Invalid event format"})

    try:
        # Route dispatch — order matters: /agents/search before /agents/{id}
        if path == "/agents" and method == "POST":
            return create_agent(event)
        elif path == "/agents" and method == "GET":
            return list_agents()
        elif path == "/agents/search" and method == "GET":
            return search_agents(event)
        elif path.startswith("/agents/") and path.endswith("/health") and method == "POST":
            return health_heartbeat(event)
        elif path.startswith("/agents/") and method == "GET":
            return get_agent(event)
        elif path.startswith("/agents/") and method == "PUT":
            return update_agent(event)
        elif path.startswith("/agents/") and method == "DELETE":
            return delete_agent(event)
        else:
            return response(404, {"error": "Not found"})
    except json.JSONDecodeError:
        return response(400, {"error": "Invalid JSON body"})
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if "Bedrock" in str(type(exc)) or "bedrock" in error_code.lower():
            return response(502, {"error": "Embedding service unavailable"})
        return response(500, {"error": "Internal server error"})
    except Exception as exc:
        print(f"Unhandled error: {exc}")
        return response(500, {"error": "Internal server error"})
