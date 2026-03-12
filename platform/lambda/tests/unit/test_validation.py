"""Unit tests for utils.validation module."""

import pytest

from utils.validation import (
    ValidationError,
    validate_agent_card,
    validate_agent_id,
    validate_chat_request,
    validate_search_params,
)


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------

class TestValidationError:
    def test_stores_fields_and_message(self):
        err = ValidationError(fields=["name"], message="missing name")
        assert err.fields == ["name"]
        assert err.message == "missing name"

    def test_is_exception(self):
        err = ValidationError(fields=["x"], message="bad")
        assert isinstance(err, Exception)

    def test_str_is_message(self):
        err = ValidationError(fields=["a", "b"], message="oops")
        assert str(err) == "oops"


# ---------------------------------------------------------------------------
# validate_agent_card
# ---------------------------------------------------------------------------

class TestValidateAgentCard:
    def test_valid_card_returns_none(self):
        body = {"name": "Agent", "description": "Does stuff", "url": "https://example.com"}
        assert validate_agent_card(body) is None

    def test_non_dict_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card("not a dict")
        assert "body" in exc_info.value.fields

    def test_missing_name(self):
        body = {"description": "d", "url": "https://example.com"}
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card(body)
        assert "name" in exc_info.value.fields

    def test_missing_description(self):
        body = {"name": "n", "url": "https://example.com"}
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card(body)
        assert "description" in exc_info.value.fields

    def test_missing_url(self):
        body = {"name": "n", "description": "d"}
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card(body)
        assert "url" in exc_info.value.fields

    def test_all_fields_missing(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card({})
        assert set(exc_info.value.fields) == {"name", "description", "url"}

    def test_empty_string_name_rejected(self):
        body = {"name": "", "description": "d", "url": "https://example.com"}
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card(body)
        assert "name" in exc_info.value.fields

    def test_whitespace_only_name_rejected(self):
        body = {"name": "   ", "description": "d", "url": "https://example.com"}
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_card(body)
        assert "name" in exc_info.value.fields

    def test_extra_fields_allowed(self):
        body = {"name": "A", "description": "B", "url": "https://x.com", "skills": ["a"]}
        assert validate_agent_card(body) is None


# ---------------------------------------------------------------------------
# validate_chat_request
# ---------------------------------------------------------------------------

class TestValidateChatRequest:
    def test_valid_request_returns_none(self):
        body = {"agentId": "abc-123", "message": "Hello"}
        assert validate_chat_request(body) is None

    def test_non_dict_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_chat_request(42)
        assert "body" in exc_info.value.fields

    def test_missing_agent_id(self):
        body = {"message": "Hello"}
        with pytest.raises(ValidationError) as exc_info:
            validate_chat_request(body)
        assert "agentId" in exc_info.value.fields

    def test_missing_message(self):
        body = {"agentId": "abc"}
        with pytest.raises(ValidationError) as exc_info:
            validate_chat_request(body)
        assert "message" in exc_info.value.fields

    def test_both_missing(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_chat_request({})
        assert "agentId" in exc_info.value.fields
        assert "message" in exc_info.value.fields

    def test_empty_agent_id_rejected(self):
        body = {"agentId": "", "message": "hi"}
        with pytest.raises(ValidationError) as exc_info:
            validate_chat_request(body)
        assert "agentId" in exc_info.value.fields

    def test_whitespace_message_rejected(self):
        body = {"agentId": "abc", "message": "   "}
        with pytest.raises(ValidationError) as exc_info:
            validate_chat_request(body)
        assert "message" in exc_info.value.fields


# ---------------------------------------------------------------------------
# validate_search_params
# ---------------------------------------------------------------------------

class TestValidateSearchParams:
    def test_query_only_returns_none(self):
        assert validate_search_params({"query": "find agents"}) is None

    def test_skills_string_only_returns_none(self):
        assert validate_search_params({"skills": "python,java"}) is None

    def test_skills_list_only_returns_none(self):
        assert validate_search_params({"skills": ["python", "java"]}) is None

    def test_both_query_and_skills_returns_none(self):
        assert validate_search_params({"query": "x", "skills": "y"}) is None

    def test_neither_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_search_params({})
        assert "query" in exc_info.value.fields
        assert "skills" in exc_info.value.fields

    def test_empty_query_and_no_skills_raises(self):
        with pytest.raises(ValidationError):
            validate_search_params({"query": ""})

    def test_whitespace_query_and_no_skills_raises(self):
        with pytest.raises(ValidationError):
            validate_search_params({"query": "   "})

    def test_empty_skills_list_raises(self):
        with pytest.raises(ValidationError):
            validate_search_params({"skills": []})


# ---------------------------------------------------------------------------
# validate_agent_id
# ---------------------------------------------------------------------------

class TestValidateAgentId:
    def test_valid_id_returns_none(self):
        assert validate_agent_id("abc-123") is None

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_id("")
        assert "agentId" in exc_info.value.fields

    def test_whitespace_only_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_agent_id("   ")
        assert "agentId" in exc_info.value.fields

    def test_none_raises(self):
        with pytest.raises(ValidationError):
            validate_agent_id(None)

    def test_non_string_raises(self):
        with pytest.raises(ValidationError):
            validate_agent_id(123)
