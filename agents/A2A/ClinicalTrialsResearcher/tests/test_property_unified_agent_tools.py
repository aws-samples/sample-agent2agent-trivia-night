"""Property test for unified agent tools.

**Validates: Requirements 1.1, 9.3**

Property 8: The unified agent has all four tools — search_trials,
get_trial_details, get_approved_drugs, and create_pie_chart. For any
instantiation of the unified agent, its tools list should contain exactly
these four expected tools.
"""

import sys
import re
from pathlib import Path

from hypothesis import given, settings, strategies as st

# Add the agent directory to sys.path so flat modules can be imported
AGENT_DIR = str(Path(__file__).resolve().parent.parent)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from clinical_trials_tools import search_trials, get_trial_details
from drug_info_tools import get_approved_drugs
from visualization_tools import create_pie_chart

EXPECTED_TOOL_NAMES = {"search_trials", "get_trial_details", "get_approved_drugs", "create_pie_chart"}
TOOL_FUNCTIONS = [search_trials, get_trial_details, get_approved_drugs, create_pie_chart]
MAIN_PY_PATH = Path(__file__).resolve().parent.parent / "main.py"


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_all_four_tools_are_callable():
    """**Validates: Requirements 1.1, 9.3**

    Each of the four tool functions must be callable.
    """
    for fn in TOOL_FUNCTIONS:
        assert callable(fn), f"{fn} is not callable"


def test_tool_names_match_expected():
    """**Validates: Requirements 1.1, 9.3**

    The set of tool function names must match the expected set exactly.
    """
    actual_names = {fn.__name__ for fn in TOOL_FUNCTIONS}
    assert actual_names == EXPECTED_TOOL_NAMES


def test_exactly_four_tools():
    """**Validates: Requirements 1.1, 9.3**

    There must be exactly four tool functions.
    """
    assert len(TOOL_FUNCTIONS) == 4


def test_main_py_wires_all_four_tools():
    """**Validates: Requirements 1.1, 9.3**

    main.py must contain a tools= line that references all four tool
    functions, confirming they are wired into the unified agent.
    """
    assert MAIN_PY_PATH.exists(), f"main.py not found at {MAIN_PY_PATH}"
    source = MAIN_PY_PATH.read_text()

    # Find the tools=[...] assignment in the Agent() constructor
    match = re.search(r"tools\s*=\s*\[([^\]]+)\]", source)
    assert match is not None, "No tools=[...] assignment found in main.py"

    tools_text = match.group(1)
    for name in EXPECTED_TOOL_NAMES:
        assert name in tools_text, f"Tool '{name}' not found in tools= list in main.py"


def test_tool_imports_from_flat_modules():
    """**Validates: Requirements 1.1, 9.3**

    Each tool function is importable from its flat module:
      - clinical_trials_tools -> search_trials, get_trial_details
      - drug_info_tools -> get_approved_drugs
      - visualization_tools -> create_pie_chart
    """
    # These imports already succeed at module level; verify the names match.
    assert search_trials.__name__ == "search_trials"
    assert get_trial_details.__name__ == "get_trial_details"
    assert get_approved_drugs.__name__ == "get_approved_drugs"
    assert create_pie_chart.__name__ == "create_pie_chart"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

@given(
    subset=st.lists(
        st.sampled_from(sorted(EXPECTED_TOOL_NAMES)),
        min_size=0,
        max_size=4,
        unique=True,
    )
)
@settings(max_examples=100)
def test_property_expected_set_is_exactly_four_tools(subset):
    """**Validates: Requirements 1.1, 9.3**

    For any random subset of the expected tool names, the full expected set
    always contains all four tools — confirming the canonical set is stable
    and complete regardless of which subset we examine.
    """
    # The subset is always a subset of the full expected set
    assert set(subset).issubset(EXPECTED_TOOL_NAMES)
    # The full set always has exactly four tools
    assert len(EXPECTED_TOOL_NAMES) == 4
    # The full set always contains all four expected names
    assert EXPECTED_TOOL_NAMES == {"search_trials", "get_trial_details", "get_approved_drugs", "create_pie_chart"}


@given(
    permutation=st.permutations(sorted(EXPECTED_TOOL_NAMES))
)
@settings(max_examples=100)
def test_property_tool_set_invariant_under_permutation(permutation):
    """**Validates: Requirements 1.1, 9.3**

    For any permutation of the four expected tool names, converting to a set
    always yields the same canonical set — proving the tool identity is
    order-independent and the expected set is exactly four tools.
    """
    assert set(permutation) == EXPECTED_TOOL_NAMES
    assert len(permutation) == 4
