import pytest
from app import review_utils


def test_language_syntax_checks_python_syntax_error():
    code = "def foo(:\n    pass\n"
    findings = review_utils.language_syntax_checks(code, "Python")
    assert any(f["category"] == "syntax" or "SyntaxError" in f.get("message", "") for f in findings)


def test_language_syntax_checks_js_debug_and_equality():
    code = "console.log('hi');\nif (a == b) { return true; }"
    findings = review_utils.language_syntax_checks(code, "JavaScript")
    cats = {f["category"] for f in findings}
    assert "debug" in cats or "style" in cats


def test_build_review_result_basic_python():
    code = "def add(a, b):\n    return a + b\n"
    res = review_utils.build_review_result(code, "Python")
    assert "score" in res and "findings" in res and "complexity" in res