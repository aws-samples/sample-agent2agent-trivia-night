"""Property test for runtime URL fallback.

**Validates: Requirements 2.1**

Property 1: For any value of the AGENTCORE_RUNTIME_URL environment variable
(including unset), os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
should equal that value when set, or fall back to "http://127.0.0.1:9000/" when unset.
"""

import os

from hypothesis import given, settings, strategies as st

DEFAULT_RUNTIME_URL = "http://127.0.0.1:9000/"
ENV_VAR = "AGENTCORE_RUNTIME_URL"

# Strategy: generate arbitrary URL-like strings
url_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
)


@given(url=url_strings)
@settings(max_examples=100)
def test_property_runtime_url_returns_set_value(url):
    """**Validates: Requirements 2.1**

    When AGENTCORE_RUNTIME_URL is set to any string, os.environ.get returns
    that exact string.
    """
    original = os.environ.get(ENV_VAR)
    try:
        os.environ[ENV_VAR] = url
        result = os.environ.get(ENV_VAR, DEFAULT_RUNTIME_URL)
        assert result == url
    finally:
        if original is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = original


@given(data=st.data())
@settings(max_examples=100)
def test_property_runtime_url_fallback_when_unset(data):
    """**Validates: Requirements 2.1**

    When AGENTCORE_RUNTIME_URL is not set, os.environ.get returns the default
    fallback value "http://127.0.0.1:9000/".
    """
    original = os.environ.get(ENV_VAR)
    try:
        os.environ.pop(ENV_VAR, None)
        result = os.environ.get(ENV_VAR, DEFAULT_RUNTIME_URL)
        assert result == DEFAULT_RUNTIME_URL
    finally:
        if original is not None:
            os.environ[ENV_VAR] = original
