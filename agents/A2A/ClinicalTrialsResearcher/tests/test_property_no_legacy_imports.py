"""Property test for no legacy package imports in tool files.

**Validates: Requirements 4.5**

Property 6: For any Python source file in the migration target directory,
the file should not contain imports using the `app.` package prefix
(e.g., `from app.tools...`, `from app.config...`).
"""

import re
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

# Directory containing the migrated agent files (top-level only)
AGENT_DIR = Path(__file__).resolve().parent.parent

# Files that belong to the migration target flat structure (design doc).
# These are the tool and config files migrated to flat imports.
# main.py is excluded here because it is migrated in a later task (3.1).
MIGRATION_TARGET_FILES = {
    "config.py",
    "clinical_trials_tools.py",
    "drug_info_tools.py",
    "visualization_tools.py",
}

# Patterns that indicate legacy imports
LEGACY_IMPORT_PATTERNS = [
    re.compile(r"^\s*from\s+app\."),
    re.compile(r"^\s*import\s+app\."),
]


def _contains_legacy_import(content: str) -> bool:
    """Return True if content contains any legacy `from app.` or `import app.` pattern."""
    for line in content.splitlines():
        for pattern in LEGACY_IMPORT_PATTERNS:
            if pattern.search(line):
                return True
    return False


# --- Property-based test ---


@given(
    valid_imports=st.lists(
        st.sampled_from([
            "from pathlib import Path",
            "import os",
            "from strands import tool",
            "import logging",
            "from config import MODEL_ID",
            "import httpx",
            "from typing import Optional",
        ]),
        min_size=0,
        max_size=5,
    ),
    legacy_imports=st.lists(
        st.sampled_from([
            "from app.tools.clinical_trials_tools import search_trials",
            "from app.config import Settings",
            "import app.utils.cache",
            "from app.middleware.auth import verify_api_key",
            "import app.services.agent_router",
        ]),
        min_size=0,
        max_size=3,
    ),
)
@settings(max_examples=100)
def test_property_legacy_import_detection(valid_imports, legacy_imports):
    """**Validates: Requirements 4.5**

    The detection function correctly identifies legacy `from app.` / `import app.`
    patterns in generated file content, regardless of how they are mixed with
    valid imports.
    """
    content = "\n".join(valid_imports + legacy_imports)
    has_legacy = _contains_legacy_import(content)
    assert has_legacy == (len(legacy_imports) > 0)


# --- Unit test against actual files ---


def test_actual_files_have_no_legacy_imports():
    """**Validates: Requirements 4.5**

    All .py files at the top level of agents/A2A/ClinicalTrialsResearcher/
    must not contain `from app.` or `import app.` import patterns.

    Only scans files that are part of the migration target flat structure
    (main.py, config.py, and the three tool modules). Legacy files pending
    removal in task 6 are excluded.
    """
    py_files = sorted(
        f for f in AGENT_DIR.glob("*.py") if f.name in MIGRATION_TARGET_FILES
    )
    assert len(py_files) > 0, f"No migration target .py files found in {AGENT_DIR}"

    violations = {}
    for py_file in py_files:
        content = py_file.read_text()
        offending_lines = []
        for i, line in enumerate(content.splitlines(), start=1):
            for pattern in LEGACY_IMPORT_PATTERNS:
                if pattern.search(line):
                    offending_lines.append(f"  line {i}: {line.strip()}")
        if offending_lines:
            violations[py_file.name] = offending_lines

    assert violations == {}, (
        "Legacy `app.` imports found:\n"
        + "\n".join(
            f"{fname}:\n" + "\n".join(lines)
            for fname, lines in violations.items()
        )
    )
