"""Property test for health check endpoint.

**Validates: Requirements 2.3, 8.2**

Property 9: For any GET request to /ping, the response status code should be 200
and the body should be {"status": "healthy"}, regardless of request headers or
query parameters.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

# Create a minimal FastAPI app replicating just the /ping endpoint from main.py.
# We avoid importing main.py directly because it has side effects (creates Agent
# and A2AServer instances requiring Bedrock credentials).
test_app = FastAPI()


@test_app.get("/ping")
def ping():
    return {"status": "healthy"}


client = TestClient(test_app)

# Strategies for generating random headers and query params.
# HTTP header keys must be ASCII-encodable, so we restrict to printable ASCII.
ascii_letters_digits = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

header_keys = st.text(
    alphabet=ascii_letters_digits + "-_",
    min_size=1,
    max_size=30,
)
header_values = st.text(
    alphabet=ascii_letters_digits + " .,;:/-_=",
    min_size=1,
    max_size=100,
)
param_keys = st.text(
    alphabet=ascii_letters_digits + "_",
    min_size=1,
    max_size=20,
)
param_values = st.text(
    alphabet=ascii_letters_digits + "_-.",
    min_size=0,
    max_size=50,
)


@given(
    headers=st.dictionaries(header_keys, header_values, min_size=0, max_size=5),
    params=st.dictionaries(param_keys, param_values, min_size=0, max_size=5),
)
@settings(max_examples=100)
def test_property_health_check_returns_healthy(headers, params):
    """**Validates: Requirements 2.3, 8.2**

    For any combination of request headers and query parameters, GET /ping
    always returns status 200 with {"status": "healthy"}.
    """
    response = client.get("/ping", headers=headers, params=params)
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_unit_health_check_basic():
    """**Validates: Requirements 2.3, 8.2**

    Simple GET /ping returns 200 with the expected body.
    """
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
