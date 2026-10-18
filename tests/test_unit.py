"""Offline unit tests (no API calls). The OpenAI client is mocked where needed, so these tests
prove the local logic only; LLM integration is proven by tests/run_scenarios.py."""
import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import nbformat
import pytest

import app


@pytest.fixture(autouse=True)
def clean_data_files():
    for path in (app.LEADS_FILE, app.FEEDBACK_FILE):
        path.unlink(missing_ok=True)
    yield


# ---------- record_customer_interest ----------
def test_valid_lead_is_persisted():
    result = app.record_customer_interest("lina@example.com", "Lina Khoury", "Comfort package, Byblos")
    assert result["status"] == "recorded"
    rows = app._read_jsonl(app.LEADS_FILE)
    assert len(rows) == 1
    assert rows[0]["name"] == "Lina Khoury" and rows[0]["email"] == "lina@example.com"
    assert rows[0]["id"] == result["lead_id"]


@pytest.mark.parametrize("email", ["", "lina@gmail", "lina.example.com", "lina@@example.com",
                                   "lina @example.com", "unknown", "@example.com"])
def test_invalid_email_is_rejected_and_not_saved(email):
    result = app.record_customer_interest(email, "Lina Khoury", "Comfort package")
    assert result["status"] == "error"
    assert any("invalid_email" in e for e in result["errors"])
    assert not app.LEADS_FILE.exists()


@pytest.mark.parametrize("name", ["", " ", "unknown", "N/A", "Customer", "1234", "x"])
def test_missing_or_placeholder_name_is_rejected(name):
    result = app.record_customer_interest("lina@example.com", name, "Comfort package")
    assert result["status"] == "error"
    assert any("name" in e for e in result["errors"])
    assert not app.LEADS_FILE.exists()


def test_duplicate_lead_is_not_saved_twice():
    first = app.record_customer_interest("lina@example.com", "Lina", "Comfort")
    second = app.record_customer_interest("LINA@example.com", "Lina", "Comfort")
    assert second == {"status": "already_recorded", "lead_id": first["lead_id"]}
    assert len(app._read_jsonl(app.LEADS_FILE)) == 1


# ---------- record_feedback ----------
def test_feedback_is_persisted():
    result = app.record_feedback("Do you install solar water heaters in Tyre?")
    assert result["status"] == "recorded"
    rows = app._read_jsonl(app.FEEDBACK_FILE)
    assert rows[0]["question"] == "Do you install solar water heaters in Tyre?"


def test_empty_feedback_is_rejected():
    assert app.record_feedback("  ")["status"] == "error"
    assert not app.FEEDBACK_FILE.exists()


# ---------- tool dispatch ----------
def test_execute_tool_call_runs_allowed_tool():
    result = app.execute_tool_call("record_feedback", json.dumps({"question": "Parking?"}), ["record_feedback"])
    assert result["status"] == "recorded"


def test_execute_tool_call_blocks_tool_not_allowed_on_route():
    result = app.execute_tool_call("record_customer_interest",
                                   json.dumps({"email": "a@example.com", "name": "Al", "message": "x"}),
                                   ["record_feedback"])
    assert result["status"] == "error"
    assert not app.LEADS_FILE.exists()


@pytest.mark.parametrize("args", ["{not json", json.dumps({"unexpected": 1})])
def test_execute_tool_call_handles_bad_arguments(args):
    result = app.execute_tool_call("record_feedback", args, ["record_feedback"])
    assert result["status"] == "error" and "bad_arguments" in result["errors"][0]


def test_tool_schemas_match_required_signatures():
    specs = {s["function"]["name"]: s["function"] for s in app.openai_tool_specs(list(app.TOOL_FUNCTIONS))}
    assert set(specs["record_customer_interest"]["parameters"]["properties"]) == {"email", "name", "message"}
    assert set(specs["record_feedback"]["parameters"]["properties"]) == {"question"}
    for definition in app.TOOL_DEFINITIONS:
        assert {"name", "description", "inputSchema", "outputSchema"} <= set(definition)


# ---------- prompt, knowledge, memory ----------
def test_system_prompt_has_labeled_persona_instructions_and_knowledge():
    prompt = app.build_system_prompt("lead_collection")
    for header in ("# PERSONA", "# INSTRUCTIONS", "# BUSINESS KNOWLEDGE", "# CURRENT ROUTE: lead_collection"):
        assert header in prompt
    assert app.PERSONA in prompt and app.INSTRUCTIONS in prompt
    assert "Rania Haddad" in prompt and "$6,500" in prompt


@pytest.mark.parametrize("fact", ["Rania Haddad", "Karim Aoun", "Maya Saliba", "Elie Nassar", "2021",
                                  "$3,900", "$6,500", "$9,800", "$1,800", "$15", "$150", "1,200",
                                  "Cedar Community Bank", "6,000 cycles", "+961 1 555 0123",
                                  "hello@suncedar-energy.example", "14 Makdessi Street"])
def test_summary_and_pdf_are_consistent(fact):
    assert fact in app.BUSINESS_SUMMARY, f"{fact} missing from summary"
    assert fact in app.BUSINESS_PROFILE, f"{fact} missing from PDF"


def test_normalize_history_handles_gradio_formats_and_trims():
    history = [{"role": "user", "content": [{"type": "text", "text": "hi"}]},
               {"role": "assistant", "content": "hello", "metadata": {}},
               {"role": "assistant", "content": {"path": "file.png"}}]
    history += [{"role": "user", "content": f"m{i}"} for i in range(30)]
    clean = app.normalize_history(history)
    assert len(clean) == app.MAX_HISTORY_MESSAGES
    assert clean[-1] == {"role": "user", "content": "m29"}
    assert app.normalize_history(history[:3]) == [{"role": "user", "content": "hi"},
                                                  {"role": "assistant", "content": "hello"}]


# ---------- router / error handling with a MOCKED client ----------
def _mock_completion(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))])


def test_router_falls_back_on_unparseable_or_unknown_output(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(app, "get_client", lambda: client)
    client.chat.completions.create.return_value = _mock_completion("not json")
    assert app.route_message("hi", []).intent == "general_question"
    client.chat.completions.create.return_value = _mock_completion('{"intent": "pizza"}')
    assert app.route_message("hi", []).intent == "general_question"


def test_chat_shows_clear_error_when_api_unavailable(monkeypatch):
    def boom():
        raise RuntimeError("OPENAI_API_KEY is not set.")
    monkeypatch.setattr(app, "get_client", boom)
    reply, trace = app.chat("What packages do you offer?", [])
    assert "temporarily unavailable" in reply and "OPENAI_API_KEY" in reply
    assert "Error" in trace


def test_api_auth_error_is_explained_without_raw_api_message(monkeypatch):
    import httpx
    import openai
    err = openai.AuthenticationError("Incorrect API key provided: sk-abc***xyz",
                                     response=httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com")),
                                     body=None)
    client = MagicMock()
    client.chat.completions.create.side_effect = err
    monkeypatch.setattr(app, "get_client", lambda: client)
    reply, trace = app.chat("hello", [])
    assert "rejected our API key" in reply
    assert "sk-abc" not in reply and "sk-abc" not in trace


# ---------- notebook stays in sync with app.py ----------
def test_notebook_contains_app_code_sections():
    nb = nbformat.read(app.BASE_DIR / "business_agent.ipynb", as_version=4)
    notebook_code = "\n".join(c.source for c in nb.cells if c.cell_type == "code")
    source = (app.BASE_DIR / "app.py").read_text().split('\nif __name__ == "__main__":')[0]
    for name, body in re.findall(r"# ==== SECTION: (\w+) ====\n(.*?)(?=\n# ==== SECTION: |\Z)", source, re.S):
        assert body.strip("\n") in notebook_code, f"notebook is out of date for section {name}; run scripts/build_notebook.py"


def test_reflection_failure_keeps_draft(monkeypatch):
    import openai
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.APIConnectionError(request=MagicMock())
    monkeypatch.setattr(app, "get_client", lambda: client)
    result = app.reflect("hi", [], "general_question", [], "Hello from Sunny!")
    assert result["final_reply"] == "Hello from Sunny!" and result["verdict"] == "approved"


def test_respond_survives_malformed_tool_arguments(monkeypatch):
    """Model emits invalid JSON arguments: the tool returns an error and the turn still completes."""
    bad_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="record_feedback", arguments="{oops"),
                               model_dump=lambda **kw: {"id": "call_1", "type": "function",
                                                        "function": {"name": "record_feedback", "arguments": "{oops"}})
    replies = iter([
        _mock_completion('{"intent": "feedback", "confidence": 0.9, "reason": "test"}'),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[bad_call]))]),
        _mock_completion("Thanks for the feedback!"),
    ])
    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: next(replies)
    monkeypatch.setattr(app, "get_client", lambda: client)
    monkeypatch.setattr(app, "ENABLE_REFLECTION", False)
    result = app.respond("Great service!", [])
    assert result.reply == "Thanks for the feedback!"
    assert result.tool_calls[0]["result"]["status"] == "error"
    assert not app.FEEDBACK_FILE.exists()
