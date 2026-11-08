"""Deterministic text scanning for negotiation messages (D5-07).

Everything here is regex-based and side-effect free. It is a safety net around the LLM, not a language
model: patterns are conservative, so a false positive costs a redraft or a human review, never a breach.
Patterns cover English, Spanish and Chinese, the languages the negotiator writes and reads (spec 3.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# Recognised currency tokens. This is a recognition list for parsing, not the list of currencies the
# platform supports: that list comes from config and is passed in by the caller.
_SYMBOLS: dict[str, str] = {
    "€": "EUR",
    "$": "USD",
    "US$": "USD",
    "¥": "CNY",
    "元": "CNY",
    "RMB": "CNY",
    "£": "GBP",
    "円": "JPY",
}
_ISO_CODES = (
    "EUR",
    "USD",
    "CNY",
    "GBP",
    "JPY",
    "CHF",
    "HKD",
    "AUD",
    "CAD",
    "INR",
    "KRW",
    "SGD",
    "TWD",
    "MXN",
    "BRL",
    "RUB",
    "TRY",
    "SEK",
    "NOK",
    "DKK",
    "PLN",
    "AED",
    "THB",
    "VND",
)
_CURRENCY = r"US\$|RMB|" + "|".join(_ISO_CODES) + r"|€|\$|¥|元|£|円"
_AMOUNT = r"\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_PRICE_RE = re.compile(
    rf"(?:(?P<c1>{_CURRENCY})\s?(?P<a1>{_AMOUNT}))|(?:(?P<a2>{_AMOUNT})\s?(?P<c2>{_CURRENCY}))",
    re.IGNORECASE,
)
_QUANTITY_RE = re.compile(
    r"(?P<n>\d{1,3}(?:[.,\s]\d{3})+|\d+)\s?(?:k\s?)?"
    r"(?P<unit>units?|uds?\.?|unidades|pcs|pieces|piezas|boxes|cajas|cartons|cartones|件|个|盒|箱)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TextPrice:
    """A price found in text. ``minor`` assumes two decimals, true for every currency the platform supports."""

    minor: int
    currency: str
    raw: str


def _currency_code(token: str) -> str:
    upper = token.upper()
    return _SYMBOLS.get(token, _SYMBOLS.get(upper, upper))


def amount_to_minor(raw: str) -> int:
    """Parses ``1.234,56``, ``1,234.56``, ``4,45``, ``4.5`` or ``1 200`` into minor units (two decimals)."""
    compact = raw.replace(" ", "").replace("\u00a0", "")
    last_sep = max(compact.rfind("."), compact.rfind(","))
    if last_sep != -1 and 1 <= len(compact) - last_sep - 1 <= 2:
        integer = re.sub(r"[.,]", "", compact[:last_sep]) or "0"
        fraction = compact[last_sep + 1 :].ljust(2, "0")
    else:
        integer = re.sub(r"[.,]", "", compact) or "0"
        fraction = "00"
    return int(integer) * 100 + int(fraction)


def find_prices(text: str) -> list[TextPrice]:
    """Every amount written next to a currency code or symbol. Bare numbers are never prices."""
    prices: list[TextPrice] = []
    for m in _PRICE_RE.finditer(text):
        token = m.group("c1") or m.group("c2")
        amount = m.group("a1") or m.group("a2")
        if token is None or amount is None:
            continue
        prices.append(TextPrice(amount_to_minor(amount), _currency_code(token), m.group(0)))
    return prices


def find_quantities(text: str) -> list[int]:
    """Every number written next to a unit word (units, uds, pcs, cajas, 件, ...)."""
    quantities: list[int] = []
    for m in _QUANTITY_RE.finditer(text):
        n = int(re.sub(r"[.,\s]", "", m.group("n")))
        if re.search(r"\d\s?k\s?", m.group(0), re.IGNORECASE):
            n *= 1000
        quantities.append(n)
    return quantities


class Counterpart(StrEnum):
    """Concessions a buyer can offer in exchange for price (spec 3.1, 3.6 step 5)."""

    HIGHER_VOLUME = "higher_volume"
    PREPAYMENT = "prepayment"
    FRAMEWORK_CONTRACT = "framework_contract"
    PAYMENT_TERMS = "payment_terms"
    GUARANTEE = "guarantee"
    PENALTY = "penalty"


_COUNTERPART_PATTERNS: dict[Counterpart, re.Pattern[str]] = {
    Counterpart.PREPAYMENT: re.compile(
        r"pre-?pay|pay(?:ment)?\s+(?:in\s+)?advance|advance\s+payment|upfront|up-front|deposit|"
        r"prepago|prepagar|pag(?:o|ar|amos|aremos)\s+(?:por\s+)?(?:adelantado|anticipado)|"
        r"(?:por\s+)?adelantado|anticipo|预付|定金|预付款",
        re.IGNORECASE,
    ),
    Counterpart.FRAMEWORK_CONTRACT: re.compile(
        r"framework\s+(?:agreement|contract)|master\s+(?:supply\s+)?agreement|long-?term\s+contract|"
        r"contrato\s+marco|acuerdo\s+marco|框架协议|长期合同",
        re.IGNORECASE,
    ),
    Counterpart.PAYMENT_TERMS: re.compile(
        r"\bnet\s?\d{2,3}\b|payment\s+terms?|\d{2,3}\s?days?\s+(?:payment|credit)|deferred\s+payment|"
        r"credit\s+terms|plazo\s+de\s+pago|pago\s+a\s+\d{2,3}\s?d[ií]as|pago\s+aplazado|账期|月结",
        re.IGNORECASE,
    ),
    Counterpart.GUARANTEE: re.compile(
        r"guarantee|letter\s+of\s+credit|\bL/?C\b|bank\s+bond|surety|garant[ií]a|aval\b|carta\s+de\s+cr[eé]dito|"
        r"担保|保函|信用证",
        re.IGNORECASE,
    ),
    Counterpart.PENALTY: re.compile(
        r"penalt(?:y|ies)|liquidated\s+damages|penalizaci[oó]n|cl[aá]usula\s+penal|罚款|违约金",
        re.IGNORECASE,
    ),
}


def find_counterparts(text: str) -> frozenset[Counterpart]:
    """Counterparts a message offers or mentions. Higher volume is checked through quantities instead."""
    return frozenset(c for c, pattern in _COUNTERPART_PATTERNS.items() if pattern.search(text))


_COMMITMENT_RE = re.compile(
    r"\bwe\s+(?:hereby\s+)?accept\b|\b(?:i|we)\s+(?:will\s+)?(?:confirm|place)\s+(?:the|this|our)\s+(?:order|purchase)\b|"
    r"\bit'?s\s+a\s+deal\b|\bdeal\s+(?:done|closed)\b|\bwe\s+have\s+a\s+deal\b|\bwe\s+(?:will\s+)?(?:buy|take)\s+(?:it|them)\b|"
    r"\bwe\s+agree\s+to\s+(?:buy|purchase|the\s+price)\b|\bconsider\s+it\s+(?:sold|done)\b|"
    r"\baceptamos\b|\btrato\s+hecho\b|\bcerramos\s+(?:el\s+)?(?:trato|acuerdo|pedido)\b|"
    r"\bconfirm(?:o|amos)\s+(?:el\s+)?(?:pedido|compra)\b|\bnos\s+lo\s+quedamos\b|\bcompramos\b|"
    r"成交|我们接受|确认下单|我们下单|就这么定了",
    re.IGNORECASE,
)


def has_binding_commitment(text: str) -> bool:
    """True when the text accepts a deal or places an order. The agent negotiates, it never buys."""
    return _COMMITMENT_RE.search(text) is not None


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|net|org|cn|io|me|es)\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\+\d{1,3}[\s-]?\d[\d\s-]{5,}\d|\b\d{3}[\s-]\d{3}[\s-]\d{3,4}\b")
_MESSENGER_RE = re.compile(
    r"whats\s?app|wechat|weixin|微信|telegram|signal\s+app|skype|line\s+app|viber|qq号|\bQQ\b",
    re.IGNORECASE,
)
_OFF_PLATFORM_PAYMENT_RE = re.compile(
    r"(?:outside|off)\s+(?:the\s+)?(?:platform|site|app)|direct(?:ly)?\s+(?:bank\s+)?(?:transfer|payment|pay)|"
    r"bank\s+transfer|wire\s+(?:transfer|the\s+money)|western\s+union|moneygram|paypal\s+(?:friends|f&f)|"
    r"crypto|bitcoin|usdt|"
    r"fuera\s+de\s+la\s+plataforma|transferencia(?:\s+bancaria)?\s+directa|pago\s+directo|"
    r"平台外|私下交易|线下付款|直接转账|银行转账",
    re.IGNORECASE,
)


def has_off_platform_contact(text: str) -> bool:
    """Emails, phone numbers, URLs or messenger apps: anything that moves the conversation off-platform."""
    return any(p.search(text) for p in (_EMAIL_RE, _URL_RE, _PHONE_RE, _MESSENGER_RE))


def has_off_platform_payment(text: str) -> bool:
    return _OFF_PLATFORM_PAYMENT_RE.search(text) is not None


_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SPANISH_TAX_ID_RE = re.compile(r"\b(?:\d{8}[A-Z]|[A-HJ-NP-SUVW]\d{7}[0-9A-J]|[XYZ]\d{7}[A-Z])\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def has_sensitive_data(text: str) -> bool:
    """IBANs, card numbers (Luhn-valid) or Spanish tax ids. The negotiator must never send these."""
    if _IBAN_RE.search(text) or _SPANISH_TAX_ID_RE.search(text):
        return True
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


_SENSITIVE_REQUEST_RE = re.compile(
    r"bank\s+(?:account|details|login|statement)|account\s+number|\biban\b|swift|routing\s+number|"
    r"password|passcode|login\s+(?:details|credentials)|one-?time\s+code|\botp\b|verification\s+code|"
    r"passport|id\s+card|identity\s+card|driver'?s\s+licen[cs]e|credit\s+card|card\s+number|\bcvv\b|"
    r"tax\s+id|tax\s+number|\bnif\b|\bcif\b|social\s+security|"
    r"cuenta\s+bancaria|datos\s+bancarios|contraseña|pasaporte|\bdni\b|tarjeta\s+de\s+cr[eé]dito|"
    r"银行账户|银行卡|密码|护照|身份证|税号|验证码",
    re.IGNORECASE,
)


def asks_for_sensitive_data(text: str) -> bool:
    return _SENSITIVE_REQUEST_RE.search(text) is not None


_CLOSING_PRESSURE_RE = re.compile(
    r"\btoday\s+only\b|\bonly\s+(?:valid\s+)?today\b|\bif\s+you\s+(?:close|order|confirm|pay)\s+(?:today|now)\b|"
    r"\bclose\s+(?:it\s+)?today\b|\b(?:offer|price)\s+(?:expires|valid\s+(?:until|for))\b|\blast\s+chance\b|"
    r"\bright\s+now\b|\bwithin\s+\d+\s+(?:hours?|minutes?)\b|"
    r"\bsi\s+(?:cierras|cerr[aá]is|confirmas|pagas)\s+hoy\b|\bsolo\s+hoy\b|\boferta\s+v[aá]lida\s+hasta\b|"
    r"今天下单|今天确认|仅限今天|限时",
    re.IGNORECASE,
)


def has_closing_pressure(text: str) -> bool:
    """Closing signals such as 'X if you close today' (spec 3.6 step 6)."""
    return _CLOSING_PRESSURE_RE.search(text) is not None
