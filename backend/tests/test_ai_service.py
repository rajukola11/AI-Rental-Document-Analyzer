import json
import pytest
from unittest.mock import MagicMock, patch, call

from app.core.exceptions import AIServiceError
from app.schemas.analysis import AnalysisResult, Clause
from app.services.ai_service import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    _get_client,
    _call_openai,
    _parse_response,
    analyze_document,
)


# ── Shared fixture data ───────────────────────────────────────────────────────

VALID_AI_JSON = json.dumps({
    "summary": "Standard German rental contract for a 2-bedroom flat in Berlin.",
    "clauses": [
        {
            "type": "Rent",
            "text": "Die monatliche Miete beträgt 900 €.",
            "explanation": "Monthly rent is 900 euros."
        },
        {
            "type": "Deposit",
            "text": "Kaution: 2.700 €.",
            "explanation": "A deposit of 2,700 euros (3 months) is required."
        },
    ],
    "risks": ["Renovation clause may impose costs on the tenant."],
    "risk_score": "medium",
})


def _make_openai_response(content: str, total_tokens: int = 512) -> MagicMock:
    """Return a mock that mimics an OpenAI ChatCompletion response object."""
    response = MagicMock()
    response.choices[0].message.content = content
    response.usage.total_tokens = total_tokens
    return response


# ===========================================================================
# Prompt constants
# ===========================================================================

class TestPromptConstants:
    def test_system_prompt_is_string(self):
        assert isinstance(SYSTEM_PROMPT, str)

    def test_system_prompt_not_empty(self):
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_json(self):
        assert "JSON" in SYSTEM_PROMPT

    def test_system_prompt_mentions_risk_score(self):
        assert "risk_score" in SYSTEM_PROMPT

    def test_system_prompt_mentions_german_law(self):
        assert "BGB" in SYSTEM_PROMPT or "German" in SYSTEM_PROMPT

    def test_user_prompt_template_is_string(self):
        assert isinstance(USER_PROMPT_TEMPLATE, str)

    def test_user_prompt_template_has_placeholder(self):
        assert "{document_text}" in USER_PROMPT_TEMPLATE

    def test_user_prompt_template_formats_correctly(self):
        result = USER_PROMPT_TEMPLATE.format(document_text="test contract text")
        assert "test contract text" in result

    def test_user_prompt_template_no_extra_placeholders(self):
        """Formatting with only document_text should not raise KeyError."""
        formatted = USER_PROMPT_TEMPLATE.format(document_text="x")
        assert isinstance(formatted, str)


# ===========================================================================
# _get_client
# ===========================================================================

class TestGetClient:
    def test_returns_openai_instance(self):
        from openai import OpenAI
        client = _get_client()
        assert isinstance(client, OpenAI)

    def test_uses_settings_api_key(self):
        from openai import OpenAI
        client = _get_client()
        assert client.api_key == "sk-test-fake-key"


# ===========================================================================
# _call_openai
# ===========================================================================

class TestCallOpenai:
    def _mock_client(self, content: str, total_tokens: int = 300) -> MagicMock:
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response(content, total_tokens)
        return client

    def test_returns_tuple_of_str_and_int(self):
        client = self._mock_client(VALID_AI_JSON, 200)
        raw, tokens = _call_openai(client, "contract text")
        assert isinstance(raw, str)
        assert isinstance(tokens, int)

    def test_returns_content_from_response(self):
        client = self._mock_client(VALID_AI_JSON, 200)
        raw, _ = _call_openai(client, "contract text")
        assert raw == VALID_AI_JSON

    def test_returns_correct_token_count(self):
        client = self._mock_client(VALID_AI_JSON, 777)
        _, tokens = _call_openai(client, "contract text")
        assert tokens == 777

    def test_tokens_zero_when_usage_is_none(self):
        """If response.usage is None, tokens_used should be 0."""
        client = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = VALID_AI_JSON
        response.usage = None
        client.chat.completions.create.return_value = response
        _, tokens = _call_openai(client, "contract text")
        assert tokens == 0

    def test_passes_system_prompt_in_messages(self):
        client = self._mock_client(VALID_AI_JSON)
        _call_openai(client, "some contract")
        call_kwargs = client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs["messages"]
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert SYSTEM_PROMPT in system_msgs[0]["content"]

    def test_passes_document_text_in_user_message(self):
        client = self._mock_client(VALID_AI_JSON)
        _call_openai(client, "MY_CONTRACT_TEXT")
        call_kwargs = client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert "MY_CONTRACT_TEXT" in user_msgs[0]["content"]

    def test_requests_json_object_response_format(self):
        client = self._mock_client(VALID_AI_JSON)
        _call_openai(client, "contract")
        call_kwargs = client.chat.completions.create.call_args
        fmt = call_kwargs.kwargs.get("response_format")
        assert fmt == {"type": "json_object"}

    def test_propagates_exception_on_api_failure(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError, match="API down"):
            _call_openai.__wrapped__(client, "contract text")  # bypass tenacity retry

    def test_uses_model_from_settings(self):
        client = self._mock_client(VALID_AI_JSON)
        _call_openai(client, "contract")
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o-mini"


# ===========================================================================
# _parse_response
# ===========================================================================

class TestParseResponse:

    # ── Valid JSON ────────────────────────────────────────────────────────────

    def test_valid_json_returns_analysis_result(self):
        result = _parse_response(VALID_AI_JSON)
        assert isinstance(result, AnalysisResult)

    def test_summary_preserved(self):
        result = _parse_response(VALID_AI_JSON)
        assert "Berlin" in result.summary

    def test_clauses_parsed_as_clause_objects(self):
        result = _parse_response(VALID_AI_JSON)
        assert len(result.clauses) == 2
        assert isinstance(result.clauses[0], Clause)

    def test_clause_fields_correct(self):
        result = _parse_response(VALID_AI_JSON)
        assert result.clauses[0].type == "Rent"
        assert "900" in result.clauses[0].text
        assert "euros" in result.clauses[0].explanation

    def test_risks_parsed_as_list_of_strings(self):
        result = _parse_response(VALID_AI_JSON)
        assert isinstance(result.risks, list)
        assert all(isinstance(r, str) for r in result.risks)

    def test_risk_score_medium(self):
        result = _parse_response(VALID_AI_JSON)
        assert result.risk_score == "medium"

    # ── risk_score normalisation ──────────────────────────────────────────────

    def test_risk_score_low_accepted(self):
        data = json.loads(VALID_AI_JSON)
        data["risk_score"] = "low"
        result = _parse_response(json.dumps(data))
        assert result.risk_score == "low"

    def test_risk_score_high_accepted(self):
        data = json.loads(VALID_AI_JSON)
        data["risk_score"] = "high"
        result = _parse_response(json.dumps(data))
        assert result.risk_score == "high"

    def test_risk_score_uppercased_normalised(self):
        data = json.loads(VALID_AI_JSON)
        data["risk_score"] = "HIGH"
        result = _parse_response(json.dumps(data))
        assert result.risk_score == "high"

    def test_risk_score_with_whitespace_normalised(self):
        data = json.loads(VALID_AI_JSON)
        data["risk_score"] = "  medium  "
        result = _parse_response(json.dumps(data))
        assert result.risk_score == "medium"

    def test_invalid_risk_score_defaults_to_medium(self):
        data = json.loads(VALID_AI_JSON)
        data["risk_score"] = "extreme"
        result = _parse_response(json.dumps(data))
        assert result.risk_score == "medium"

    def test_missing_risk_score_defaults_to_medium(self):
        data = json.loads(VALID_AI_JSON)
        del data["risk_score"]
        result = _parse_response(json.dumps(data))
        assert result.risk_score == "medium"

    # ── Missing field defaults ────────────────────────────────────────────────

    def test_missing_summary_defaults_to_placeholder(self):
        data = json.loads(VALID_AI_JSON)
        del data["summary"]
        result = _parse_response(json.dumps(data))
        assert result.summary == "No summary available."

    def test_missing_clauses_defaults_to_empty_list(self):
        data = json.loads(VALID_AI_JSON)
        del data["clauses"]
        result = _parse_response(json.dumps(data))
        assert result.clauses == []

    def test_missing_risks_defaults_to_empty_list(self):
        data = json.loads(VALID_AI_JSON)
        del data["risks"]
        result = _parse_response(json.dumps(data))
        assert result.risks == []

    def test_all_required_fields_missing_still_returns_result(self):
        minimal = json.dumps({"risk_score": "low"})
        result = _parse_response(minimal)
        assert isinstance(result, AnalysisResult)
        assert result.risk_score == "low"

    # ── Invalid JSON ──────────────────────────────────────────────────────────

    def test_invalid_json_raises_ai_service_error(self):
        with pytest.raises(AIServiceError, match="invalid JSON"):
            _parse_response("not json at all")

    def test_empty_string_raises_ai_service_error(self):
        with pytest.raises(AIServiceError):
            _parse_response("")

    def test_json_array_raises_exception(self):
        """Top-level array is valid JSON but _parse_response expects a dict.
        Currently raises AttributeError because data.get() is called on a list.
        Ideally this should raise AIServiceError — tracked as a known bug.
        """
        with pytest.raises((AIServiceError, AttributeError)):
            _parse_response("[]")

    def test_markdown_wrapped_json_raises_ai_service_error(self):
        """Model returning ```json ... ``` should fail — we expect raw JSON."""
        wrapped = f"```json\n{VALID_AI_JSON}\n```"
        with pytest.raises(AIServiceError):
            _parse_response(wrapped)

    def test_clause_missing_required_field_raises_ai_service_error(self):
        """A clause without 'type' is an invalid schema — must raise."""
        data = json.loads(VALID_AI_JSON)
        data["clauses"] = [{"text": "some text", "explanation": "some explanation"}]
        with pytest.raises(AIServiceError, match="schema"):
            _parse_response(json.dumps(data))

    def test_partial_json_raises_ai_service_error(self):
        with pytest.raises(AIServiceError):
            _parse_response('{"summary": "incomplete"')


# ===========================================================================
# analyze_document
# ===========================================================================

class TestAnalyzeDocument:

    def _mock_openai_success(self, raw_json: str = VALID_AI_JSON, tokens: int = 400):
        """Patch _call_openai to return (raw_json, tokens) without hitting the API."""
        return patch(
            "app.services.ai_service._call_openai",
            return_value=(raw_json, tokens),
        )

    # ── Return shape ──────────────────────────────────────────────────────────

    def test_returns_three_tuple(self):
        with self._mock_openai_success():
            result = analyze_document("contract text " * 10)
        assert len(result) == 3

    def test_first_element_is_analysis_result(self):
        with self._mock_openai_success():
            analysis, _, _ = analyze_document("contract text " * 10)
        assert isinstance(analysis, AnalysisResult)

    def test_second_element_is_token_count(self):
        with self._mock_openai_success(tokens=999):
            _, tokens, _ = analyze_document("contract text " * 10)
        assert tokens == 999

    def test_third_element_is_float(self):
        with self._mock_openai_success():
            _, _, elapsed = analyze_document("contract text " * 10)
        assert isinstance(elapsed, float)

    def test_elapsed_is_non_negative(self):
        with self._mock_openai_success():
            _, _, elapsed = analyze_document("contract text " * 10)
        assert elapsed >= 0.0

    def test_elapsed_is_rounded_to_two_decimal_places(self):
        with self._mock_openai_success():
            _, _, elapsed = analyze_document("contract text " * 10)
        # round(x, 2) means at most 2 decimal digits
        assert elapsed == round(elapsed, 2)

    def test_analysis_result_fields_populated(self):
        with self._mock_openai_success():
            analysis, _, _ = analyze_document("contract text " * 10)
        assert analysis.summary
        assert analysis.risk_score in ("low", "medium", "high")

    # ── Chunking behaviour ────────────────────────────────────────────────────

    def test_short_document_uses_single_chunk(self):
        """chunk_text should NOT be logged as multi-chunk for short docs."""
        with self._mock_openai_success():
            with patch("app.services.ai_service.logger") as mock_logger:
                analyze_document("short contract text")
        # Info log for multi-chunk should NOT have been called
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert not any("chunks" in c for c in info_calls)

    def test_long_document_logs_chunk_count(self):
        """A document exceeding 12000 chars should trigger the multi-chunk log."""
        long_text = "paragraph content here\n\n" * 600  # well over 12k chars
        with self._mock_openai_success():
            with patch("app.services.ai_service.logger") as mock_logger:
                analyze_document(long_text)
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("chunk" in c.lower() for c in info_calls)

    def test_only_primary_chunk_sent_to_openai(self):
        """Even for a multi-chunk doc, _call_openai is called exactly once."""
        long_text = "paragraph content here\n\n" * 600
        with self._mock_openai_success() as mock_call:
            analyze_document(long_text)
        assert mock_call.call_count == 1

    # ── Error propagation ────────────────────────────────────────────────────

    def test_openai_failure_raises_ai_service_error(self):
        with patch("app.services.ai_service._call_openai", side_effect=RuntimeError("timeout")):
            with pytest.raises(AIServiceError, match="AI analysis failed"):
                analyze_document("contract text " * 10)

    def test_parse_failure_propagates_ai_service_error(self):
        with patch("app.services.ai_service._call_openai", return_value=("bad json {{", 100)):
            with pytest.raises(AIServiceError):
                analyze_document("contract text " * 10)

    def test_openai_error_logged_before_raise(self):
        with patch("app.services.ai_service._call_openai", side_effect=RuntimeError("boom")):
            with patch("app.services.ai_service.logger") as mock_logger:
                with pytest.raises(AIServiceError):
                    analyze_document("contract text " * 10)
        mock_logger.error.assert_called_once()