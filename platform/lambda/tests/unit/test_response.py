"""Unit tests for utils.response module."""

import json

from utils.response import (
    CORS_HEADERS,
    ERROR_CODE_MAP,
    build_error_response,
    build_success_response,
)


# ---------------------------------------------------------------------------
# build_success_response
# ---------------------------------------------------------------------------

class TestBuildSuccessResponse:
    def test_default_status_code(self):
        resp = build_success_response({"ok": True})
        assert resp["statusCode"] == 200

    def test_custom_status_code(self):
        resp = build_success_response({"id": "abc"}, status_code=201)
        assert resp["statusCode"] == 201

    def test_body_is_json_string(self):
        payload = {"items": [1, 2, 3]}
        resp = build_success_response(payload)
        assert json.loads(resp["body"]) == payload

    def test_cors_headers_present(self):
        resp = build_success_response({})
        for key in ("Access-Control-Allow-Origin", "Access-Control-Allow-Headers", "Access-Control-Allow-Methods"):
            assert key in resp["headers"]

    def test_allow_origin_star(self):
        resp = build_success_response({})
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_request_id_header_included(self):
        resp = build_success_response({}, request_id="req-123")
        assert resp["headers"]["X-Request-ID"] == "req-123"

    def test_request_id_header_absent_when_none(self):
        resp = build_success_response({})
        assert "X-Request-ID" not in resp["headers"]


# ---------------------------------------------------------------------------
# build_error_response
# ---------------------------------------------------------------------------

class TestBuildErrorResponse:
    def test_400_maps_to_validation_error(self):
        resp = build_error_response(400, "bad input")
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_404_maps_to_not_found(self):
        resp = build_error_response(404, "not found")
        body = json.loads(resp["body"])
        assert body["error_code"] == "NOT_FOUND"

    def test_502_maps_to_agent_unreachable(self):
        resp = build_error_response(502, "timeout")
        body = json.loads(resp["body"])
        assert body["error_code"] == "AGENT_UNREACHABLE"

    def test_500_maps_to_internal_error(self):
        resp = build_error_response(500, "oops")
        body = json.loads(resp["body"])
        assert body["error_code"] == "INTERNAL_ERROR"

    def test_unknown_status_falls_back_to_internal_error(self):
        resp = build_error_response(503, "unavailable")
        body = json.loads(resp["body"])
        assert body["error_code"] == "INTERNAL_ERROR"

    def test_explicit_error_code_overrides_mapping(self):
        resp = build_error_response(400, "custom", error_code="CUSTOM_CODE")
        body = json.loads(resp["body"])
        assert body["error_code"] == "CUSTOM_CODE"

    def test_error_body_structure(self):
        resp = build_error_response(400, "missing name", details={"field": "name"})
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["message"] == "missing name"
        assert body["details"] == {"field": "name"}

    def test_details_default_to_empty_dict(self):
        resp = build_error_response(500, "fail")
        body = json.loads(resp["body"])
        assert body["details"] == {}

    def test_cors_headers_present(self):
        resp = build_error_response(500, "fail")
        for key in ("Access-Control-Allow-Origin", "Access-Control-Allow-Headers", "Access-Control-Allow-Methods"):
            assert key in resp["headers"]

    def test_request_id_header(self):
        resp = build_error_response(404, "gone", request_id="req-456")
        assert resp["headers"]["X-Request-ID"] == "req-456"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_error_code_map_keys(self):
        assert set(ERROR_CODE_MAP.keys()) == {400, 404, 500, 502}

    def test_cors_headers_has_required_keys(self):
        assert "Access-Control-Allow-Origin" in CORS_HEADERS
        assert "Access-Control-Allow-Headers" in CORS_HEADERS
        assert "Access-Control-Allow-Methods" in CORS_HEADERS
