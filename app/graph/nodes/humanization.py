import re
from typing import List, Tuple

_ROBOTIC_PATTERNS = (
    r"\bcomo assistente virtual\b",
    r"\bprezad[oa]\b",
    r"\batenciosamente\b",
    r"\bficamos a disposicao\b",
    r"\bestamos a disposicao\b",
    r"\bquaisquer esclarecimentos\b",
    r"\bpoderia(?:m)?\b",
    r"\bagradecemos o contato\b",
)

_LIST_OR_MARKDOWN_PATTERN = re.compile(r"(?m)^\s*(?:[-*]|\d+[.)])\s+|```|[*_]{2,}|^\s*#")
_EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF]")


def find_robotic_issues(text: str) -> List[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return ["empty"]

    issues: List[str] = []
    lowered = cleaned.lower()

    if any(re.search(pattern, lowered) for pattern in _ROBOTIC_PATTERNS):
        issues.append("formal_or_robotic_phrase")

    if _LIST_OR_MARKDOWN_PATTERN.search(cleaned):
        issues.append("list_or_markdown_format")

    if cleaned.count("?") > 1:
        issues.append("multiple_questions")

    if len([line for line in cleaned.splitlines() if line.strip()]) > 4:
        issues.append("too_many_lines")

    if len(cleaned) > 420:
        issues.append("too_long")

    if len(_EMOJI_PATTERN.findall(cleaned)) > 1:
        issues.append("too_many_emoji")

    return issues


def enforce_humanized_response(candidate: str, fallback: str) -> Tuple[str, List[str]]:
    cleaned_candidate = (candidate or "").strip()
    cleaned_fallback = (fallback or "").strip()

    if not cleaned_candidate:
        return cleaned_fallback, ["empty"]

    issues = find_robotic_issues(cleaned_candidate)
    if issues and cleaned_fallback:
        return cleaned_fallback, issues
    return cleaned_candidate, issues
