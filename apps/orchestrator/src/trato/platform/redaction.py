"""Shared redaction rules: secrets and financial values never reach logs, traces or Sentry.

The same rules are implemented in TypeScript (`apps/browser-worker/src/platform/redaction.ts`).
Both implementations must agree on `docs/observability/redaction-vectors.json`.

Rule summary (full contract in `docs/observability/README.md`):
- Key-based: a dict key is sensitive when, after splitting it into words (camelCase and any
  non-alphanumeric separator), it contains a sensitive word, a sensitive phrase, a `token` or
  `signature` word without an allowed modifier, a `minor`/`bp` word, or a financial metric name.
  A sensitive key's value is replaced entirely.
- Value-based: well-known secret shapes are replaced wherever they appear in a string.
- Fail closed: any unexpected error replaces the offending value with `[REDACTED]` and increments
  `stats.errors`. The redactor never raises.
"""

from __future__ import annotations

import re
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

REDACTED = "[REDACTED]"
MAX_DEPTH = 32

FINANCIAL_METRICS: tuple[str, ...] = (
    "cash_balance",
    "credit_line_available",
    "credit_line_limit",
    "accounts_receivable",
    "accounts_payable",
    "revenue",
    "cogs",
    "fixed_costs",
    "payroll",
    "debt_service",
    "capex",
    "tax_reserve",
    "safety_buffer_pct",
    "payment_term_days",
)
FINANCIAL_KEYWORDS: tuple[str, ...] = (
    "value_minor",
    "value_bp",
    "amount_minor",
    "iban",
    "bank_account",
    "buying_power",
    "budget",
    "envelope",
)

_SENSITIVE_PARTS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "authorization",
        "cookie",
        "cookies",
        "apikey",
        "privatekey",
        "iban",
        "envelope",
        "envelopes",
        "budget",
    }
)
_SENSITIVE_PHRASES: tuple[tuple[str, ...], ...] = (
    ("api", "key"),
    ("private", "key"),
    ("session", "state"),
    ("buying", "power"),
    ("bank", "account"),
)
_TOKEN_MODIFIERS = frozenset(
    {
        "count",
        "counts",
        "usage",
        "limit",
        "max",
        "type",
        "ratio",
        "cost",
        "budget",
        "expires",
        "expiry",
        "ttl",
        "at",
    }
)
_SIGNATURE_MODIFIERS = frozenset(
    {
        "status",
        "id",
        "ids",
        "hash",
        "count",
        "at",
        "version",
        "band",
        "model",
        "valid",
        "verified",
        "algorithm",
        "alg",
        "type",
    }
)
_SUFFIX_PARTS = frozenset({"minor", "bp"})
_FINANCIAL_PHRASES: tuple[tuple[str, ...], ...] = tuple(
    tuple(metric.split("_")) for metric in FINANCIAL_METRICS + FINANCIAL_KEYWORDS
)

_KEYWORD_ALTERNATION = "|".join(
    [
        "password",
        "passwd",
        "secret",
        "token",
        "api[_-]?key",
        "authorization",
        "cookie",
        "credential",
        "private[_-]?key",
        "session[_-]?state",
        "bank[_-]?account",
        "buying[_-]?power",
        "budget",
        "envelope",
        *FINANCIAL_METRICS,
        *FINANCIAL_KEYWORDS,
    ]
)

_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
        ),
        REDACTED,
    ),
    (re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]+"), REDACTED),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), REDACTED),
    (
        re.compile(r"((?:authorization|set-cookie|cookie)\s*[:=]\s*)[^\r\n]+", re.IGNORECASE),
        "\\1" + REDACTED,
    ),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE), REDACTED),
    (re.compile(r"\bhv[sbr]\.[A-Za-z0-9_-]{16,}"), REDACTED),
    (re.compile(r"\bs\.[A-Za-z0-9]{24}\b"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), REDACTED),
    (re.compile(r"\b[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]{4}){2,8}(?: ?[A-Z0-9]{1,4})?\b"), REDACTED),
    (re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@]+@"), "\\1" + REDACTED + "@"),
    (
        re.compile(
            rf"((?:{_KEYWORD_ALTERNATION})[A-Za-z0-9_.-]*[\"']?\s*[=:]\s*[\"']?)"
            r"([^\s\"',;&}\[\]]+)",
            re.IGNORECASE,
        ),
        "\\1" + REDACTED,
    ),
)


@dataclass
class RedactionStats:
    """In-process counters. Exposed for health checks; never contain redacted content."""

    matches: int = 0
    errors: int = 0


stats = RedactionStats()


def _key_parts(key: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [part for part in re.split(r"[^a-z0-9]+", spaced.lower()) if part]


def _has_phrase(parts: list[str], phrase: tuple[str, ...]) -> bool:
    size = len(phrase)
    return any(tuple(parts[i : i + size]) == phrase for i in range(len(parts) - size + 1))


def is_sensitive_key(key: str) -> bool:
    """Return True when a dict key names a secret or a financial value."""
    parts = _key_parts(key)
    if not parts:
        return False
    words = set(parts)
    if words & _SENSITIVE_PARTS or words & _SUFFIX_PARTS:
        return True
    if any(_has_phrase(parts, phrase) for phrase in _SENSITIVE_PHRASES):
        return True
    if "token" in words and not words & _TOKEN_MODIFIERS:
        return True
    if words & {"signature", "signatures"} and not words & _SIGNATURE_MODIFIERS:
        return True
    return any(_has_phrase(parts, phrase) for phrase in _FINANCIAL_PHRASES)


def redact_text(text: str) -> str:
    """Replace secret-shaped substrings and `keyword=value` pairs in free text."""
    result = text
    try:
        for pattern, replacement in _VALUE_PATTERNS:
            result, count = pattern.subn(replacement, result)
            stats.matches += count
    except Exception:
        stats.errors += 1
        return REDACTED
    return result


def redact_value(value: Any, _depth: int = 0) -> Any:
    """Return a copy of `value` with secrets and financial values replaced. Never raises."""
    if _depth > MAX_DEPTH:
        stats.errors += 1
        return REDACTED
    try:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, Mapping):
            out: dict[Any, Any] = {}
            for key, item in value.items():
                if is_sensitive_key(str(key)):
                    stats.matches += 1
                    out[key] = REDACTED
                else:
                    out[key] = redact_value(item, _depth + 1)
            return out
        if isinstance(value, list):
            return [redact_value(item, _depth + 1) for item in value]
        if isinstance(value, tuple):
            return tuple(redact_value(item, _depth + 1) for item in value)
        if isinstance(value, BaseException):
            return {
                "type": type(value).__name__,
                "message": redact_text(str(value)),
                "stack": redact_text("".join(traceback.format_exception(value))),
            }
        if isinstance(value, bytes):
            return redact_text(value.decode("utf-8", errors="replace"))
        return value
    except Exception:
        stats.errors += 1
        return REDACTED


def redact_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Redact a flat attribute mapping (span attributes, log extras, Sentry tags)."""
    redacted = redact_value(dict(attributes))
    return redacted if isinstance(redacted, dict) else {}
