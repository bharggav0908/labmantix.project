import ast
import json
import re
from typing import Any

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


def heuristic_review(code: str, language: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = code.splitlines()

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"\b(eval|exec)\s*\(", stripped):
            findings.append({
                "line": index,
                "severity": "high",
                "category": "security",
                "message": "Dynamic code execution can be unsafe and should be avoided when possible.",
            })
        if re.search(r"password|secret|api[_-]?key", stripped, re.IGNORECASE):
            findings.append({
                "line": index,
                "severity": "high",
                "category": "security",
                "message": "Hard-coded secrets detected. Move them to environment variables.",
            })
        if len(stripped) > 140:
            findings.append({
                "line": index,
                "severity": "medium",
                "category": "readability",
                "message": "This line is long. Consider refactoring it for readability.",
            })
        if re.search(r"\bTODO\b", stripped, re.IGNORECASE):
            findings.append({
                "line": index,
                "severity": "low",
                "category": "maintainability",
                "message": "A TODO marker was found. Plan and remove it once implemented.",
            })

    if len(lines) > 180:
        findings.append({
            "line": 1,
            "severity": "medium",
            "category": "maintainability",
            "message": "The file is quite large. Consider splitting it into smaller modules.",
        })

    if not findings:
        findings.append({
            "line": 1,
            "severity": "info",
            "category": "general",
            "message": f"No obvious issues detected for {language or 'this code'}.",
        })

    return findings


def ai_review(code: str, language: str) -> list[dict[str, Any]]:
    api_key = None
    try:
        import os

        api_key = os.getenv("OPENAI_API_KEY")
    except Exception:
        api_key = None

    if not api_key or OpenAI is None:
        return heuristic_review(code, language)

    client = OpenAI(api_key=api_key)
    prompt = f"""
You are a senior engineer reviewing code for bugs, security, performance, readability, and maintainability.
Language: {language or 'unknown'}
Code:
{code}
Return 3-6 concise review findings as JSON with fields: line, severity, category, message.
"""
    response = client.responses.create(model="gpt-4o-mini", input=prompt, temperature=0.2)
    text = response.output_text.strip()
    try:
        payload = text if text.startswith("[") else text[text.find("["): text.rfind("]") + 1]
        return json.loads(payload)
    except Exception:
        return heuristic_review(code, language)


def analyze_complexity(code: str) -> dict[str, Any]:
    lines = code.splitlines()
    function_count = len(re.findall(r"\bdef\s+\w+\s*\(", code)) + len(re.findall(r"\bfunction\s+\w+\s*\(", code))
    class_count = len(re.findall(r"\bclass\s+\w+", code))
    loop_count = len(re.findall(r"\b(for|while)\b", code))
    conditional_count = len(re.findall(r"\b(if|elif|else|switch)\b", code))
    complexity_score = min(100, 10 + function_count * 5 + class_count * 4 + loop_count * 3 + conditional_count * 2)
    return {
        "total_lines": max(1, len(lines)),
        "function_count": function_count,
        "class_count": class_count,
        "loop_count": loop_count,
        "conditional_count": conditional_count,
        "overall_complexity": complexity_score,
    }


def language_syntax_checks(code: str, language: str) -> list[dict[str, Any]]:
    """Run lightweight, language-specific syntax checks and return findings.

    This is a heuristic layer — for full checks integrate linters (pylint, eslint).
    """
    findings: list[dict[str, Any]] = []
    lang = (language or "").lower()

    # Python: try parsing AST to catch real syntax errors
    if "python" in lang:
        try:
            ast.parse(code)
        except SyntaxError as e:
            findings.append({
                "line": getattr(e, "lineno", 1) or 1,
                "severity": "high",
                "category": "syntax",
                "message": f"Python SyntaxError: {e.msg}",
            })

    # JavaScript / TypeScript heuristics
    if lang in ("javascript", "js", "typescript", "ts"):
        # discourage == in favor of ===
        if re.search(r"(?<![=!])==(?!=)", code):
            findings.append({"line": 1, "severity": "medium", "category": "style", "message": "Use '===' instead of '==' for strict equality in JavaScript."})
        # detect common debug statements
        if re.search(r"\bconsole\.log\s*\(", code):
            findings.append({"line": 1, "severity": "low", "category": "debug", "message": "Found console.log() — remove debug logs in production code."})

    # Java heuristics
    if "java" in lang:
        if re.search(r"System\.out\.println\s*\(", code):
            findings.append({"line": 1, "severity": "low", "category": "debug", "message": "Found System.out.println() — remove debug prints for production."})

    # C / C++ heuristics (very lightweight)
    if lang in ("c", "c++", "cpp"):
        # look for missing semicolon patterns (very heuristic)
        for i, line in enumerate(code.splitlines(), start=1):
            s = line.strip()
            if s and not s.endswith(";") and not s.endswith("{") and not s.endswith("}") and not s.startswith("#") and "(" in s and ")" in s and not s.startswith("if"):
                findings.append({"line": i, "severity": "medium", "category": "syntax", "message": "Possible missing semicolon or incomplete statement."})

    # Generic checks across languages
    if re.search(r"password|secret|api[_-]?key", code, re.IGNORECASE):
        findings.append({"line": 1, "severity": "high", "category": "security", "message": "Hard-coded secret detected. Move to environment variables or secret manager."})

    return findings


def build_review_result(code: str, language: str) -> dict[str, Any]:
    findings = ai_review(code, language)
    # Add language-specific syntax and heuristic checks
    lang_findings = language_syntax_checks(code, language)
    if lang_findings:
        findings = lang_findings + findings
    complexity = analyze_complexity(code)
    severity_counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        severity_counts[str(finding.get("severity", "info")).lower()] += 1
    score = max(0, min(100, 100 - severity_counts["high"] * 16 - severity_counts["medium"] * 8 - severity_counts["low"] * 4))
    summary = (
        f"Reviewed {language or 'unknown'} code and found {len(findings)} observations. "
        f"The overall quality score is {score}/100."
    )
    return {
        "findings": findings,
        "complexity": complexity,
        "score": score,
        "summary": summary,
    }
