"""
Regression tests for report HTML escaping and the session-feedback LLM call.

Run with: pytest backend/app/tests/test_reports_and_feedback.py -v
"""

import asyncio
import sys
import types
from unittest.mock import patch, MagicMock

PAYLOAD = '<img src="http://169.254.170.2/creds"><script>alert(1)</script>'


def _report_with(text):
    return {
        "header": {"title": text, "user_name": text},
        "executive_summary": {"assessment": text, "overall_score": 72},
        "score_breakdown": {"content": {"label": text, "score": 80}},
        "strengths_summary": [text],
        "improvement_priorities": [{"area": text, "action_plan": text}],
        "questions_analysis": [{
            "number": 1, "question": text, "feedback_summary": text,
            "scores": {"final": 70}, "duration_seconds": 30,
        }],
        "action_plan": {"immediate": [text], "short_term": [text]},
        "footer": {"disclaimer": text},
    }


def test_report_html_escapes_user_text():
    from app.services.report_generation_service import generate_pdf_html
    html = generate_pdf_html(_report_with(PAYLOAD))
    assert "<img" not in html
    assert "<script>" not in html
    assert "&lt;img" in html


def test_report_html_keeps_scores():
    from app.services.report_generation_service import generate_pdf_html
    html = generate_pdf_html(_report_with("Plain text"))
    assert "72/100" in html
    assert "Plain text" in html


def test_session_feedback_uses_llm_settings():
    """_call_gemini_async must use LLM_API_KEY / LLM_MODEL (it used to read
    settings that don't exist and silently return nothing)."""
    from app.services import dynamic_feedback_service as dfs

    fake_genai = types.ModuleType("google.generativeai")
    fake_genai.configure = MagicMock()
    model = MagicMock()
    model.generate_content.return_value = MagicMock(text='{"ok": true}')
    fake_genai.GenerativeModel = MagicMock(return_value=model)
    fake_google = types.ModuleType("google")
    fake_google.generativeai = fake_genai

    with patch.dict(sys.modules, {"google": fake_google, "google.generativeai": fake_genai}), \
         patch.object(dfs.settings, "llm_api_key", "test-key"), \
         patch.object(dfs.settings, "llm_model", "gemini-test-model"):
        result = asyncio.run(dfs._call_gemini_async("prompt"))

    assert result == '{"ok": true}'
    fake_genai.configure.assert_called_once_with(api_key="test-key")
    assert fake_genai.GenerativeModel.call_args.kwargs["model_name"] == "gemini-test-model"
