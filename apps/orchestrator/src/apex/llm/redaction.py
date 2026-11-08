"""Outgoing-message guard (criterion 29, spec §5.6).

Every outgoing request is checked before transport. Default action is ``reject`` (raises
:class:`RedactionViolation`); ``mask`` replaces findings with placeholders. Detected classes:

- bearer tokens, ``sk-…`` style API keys, JWTs, PEM private-key blocks;
- IBAN (mod-97 validated) and payment card numbers (Luhn validated);
- any literal the caller flagged as sensitive (e.g. the tenant's cash balance strings).

The violation error reports the *class* of each finding, never the matched value.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class RedactionAction(StrEnum):
    REJECT = "reject"
    MASK = "mask"


class RedactionViolation(Exception):
    """A message contained credentials or sensitive financial data. Carries classes, not values."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = findings
        super().__init__(f"outgoing LLM message blocked: {', '.join(sorted(set(findings)))}")


@dataclass(frozen=True)
class _Finding:
    kind: str
    start: int
    end: int


_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
_SK_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _iban_ok(candidate: str) -> bool:
    compact = candidate.replace(" ", "").upper()
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


def _find(text: str, sensitive_values: Iterable[str]) -> list[_Finding]:
    findings: list[_Finding] = []
    for pattern, kind in (
        (_PEM, "private_key"),
        (_BEARER, "bearer_token"),
        (_SK_KEY, "api_key"),
        (_JWT, "jwt"),
    ):
        findings.extend(_Finding(kind, m.start(), m.end()) for m in pattern.finditer(text))
    for match in _IBAN.finditer(text):
        if _iban_ok(match.group(0)):
            findings.append(_Finding("iban", match.start(), match.end()))
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            findings.append(_Finding("card_number", match.start(), match.end()))
    for value in sensitive_values:
        if not value:
            continue
        for match in re.finditer(re.escape(value), text):
            findings.append(_Finding("sensitive_value", match.start(), match.end()))
    return findings


def _mask(text: str, findings: list[_Finding]) -> str:
    merged: list[_Finding] = []
    for finding in sorted(findings, key=lambda f: (f.start, -f.end)):
        if merged and finding.start < merged[-1].end:
            last = merged[-1]
            merged[-1] = _Finding(last.kind, last.start, max(last.end, finding.end))
        else:
            merged.append(finding)
    result = text
    for finding in reversed(merged):
        result = result[: finding.start] + f"[REDACTED:{finding.kind}]" + result[finding.end :]
    return result


class RedactionGuard:
    """Checks (and optionally masks) message content before it leaves the process."""

    def __init__(self, action: RedactionAction = RedactionAction.REJECT) -> None:
        self.action = action

    def check_text(self, text: str, sensitive_values: Iterable[str] = ()) -> str:
        findings = _find(text, sensitive_values)
        if not findings:
            return text
        if self.action is RedactionAction.REJECT:
            raise RedactionViolation([f.kind for f in findings])
        return _mask(text, findings)

    def check_messages(
        self,
        messages: list[dict[str, str]],
        sensitive_values: Iterable[str] = (),
    ) -> list[dict[str, str]]:
        values = list(sensitive_values)
        cleaned: list[dict[str, str]] = []
        all_findings: list[str] = []
        for message in messages:
            content = str(message.get("content", ""))
            findings = _find(content, values)
            if findings and self.action is RedactionAction.REJECT:
                all_findings.extend(f.kind for f in findings)
                continue
            if findings:
                content = _mask(content, findings)
            cleaned.append({**message, "content": content})
        if all_findings:
            raise RedactionViolation(all_findings)
        return cleaned


__all__ = ["RedactionAction", "RedactionGuard", "RedactionViolation"]
