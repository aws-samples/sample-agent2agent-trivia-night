"""Property test for excluded dependencies absent from requirements.txt.

**Validates: Requirements 7.7**

Property 7: For any line in requirements.txt, it should not match any of the
excluded packages: pydantic-settings, mangum, or redis.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

# Path to the actual requirements.txt
REQUIREMENTS_PATH = Path(__file__).resolve().parent.parent / "requirements.txt"

EXCLUDED_PACKAGES = ["pydantic-settings", "mangum", "redis"]


def _line_contains_excluded_package(line: str) -> bool:
    """Check if a requirements.txt line matches an excluded package."""
    stripped = line.strip().lower()
    if not stripped or stripped.startswith("#"):
        return False
    # Extract the package name (before any version specifier)
    pkg_name = stripped.split("==")[0].split(">=")[0].split("<=")[0]
    pkg_name = pkg_name.split("!=")[0].split("~=")[0].split("[")[0].split("<")[0].split(">")[0]
    pkg_name = pkg_name.strip()
    return pkg_name in EXCLUDED_PACKAGES


# --- Property-based test ---

@given(
    valid_deps=st.lists(
        st.sampled_from(["strands-agents[a2a]", "boto3", "httpx", "matplotlib", "curl-cffi", "bedrock_agentcore"]),
        min_size=1,
        max_size=10,
    ),
    excluded_deps=st.lists(
        st.sampled_from(EXCLUDED_PACKAGES),
        min_size=0,
        max_size=5,
    ),
)
@settings(max_examples=100)
def test_property_excluded_deps_detected_in_generated_content(valid_deps, excluded_deps):
    """**Validates: Requirements 7.7**

    For any generated requirements.txt content that includes excluded packages
    mixed with valid ones, the detection function correctly identifies them.
    """
    lines = valid_deps + excluded_deps
    found_excluded = [line for line in lines if _line_contains_excluded_package(line)]
    assert set(found_excluded) == set(excluded_deps)


# --- Unit test against actual requirements.txt ---

def test_actual_requirements_excludes_forbidden_packages():
    """**Validates: Requirements 7.7**

    The actual requirements.txt file must not contain pydantic-settings,
    mangum, or redis.
    """
    assert REQUIREMENTS_PATH.exists(), f"requirements.txt not found at {REQUIREMENTS_PATH}"
    content = REQUIREMENTS_PATH.read_text()
    lines = content.splitlines()
    violations = [line for line in lines if _line_contains_excluded_package(line)]
    assert violations == [], f"Excluded packages found in requirements.txt: {violations}"
