"""Deterministic text scanners for negotiation messages (D5-07), in English, Spanish and Chinese."""

import pytest

from apex.negotiation.text import (
    Counterpart,
    amount_to_minor,
    asks_for_sensitive_data,
    find_counterparts,
    find_prices,
    find_quantities,
    has_binding_commitment,
    has_closing_pressure,
    has_off_platform_contact,
    has_off_platform_payment,
    has_sensitive_data,
)


@pytest.mark.parametrize(
    ("raw", "minor"),
    [
        pytest.param("4.45", 445, id="dot-decimal"),
        pytest.param("4,45", 445, id="comma-decimal"),
        pytest.param("4.5", 450, id="single-decimal-digit"),
        pytest.param("1.234,56", 123456, id="eu-thousands-and-decimal"),
        pytest.param("1,234.56", 123456, id="us-thousands-and-decimal"),
        pytest.param("1 200", 120000, id="space-thousands"),
        pytest.param("12", 1200, id="integer"),
        pytest.param("0,05", 5, id="leading-zero-decimal"),
    ],
)
def test_amount_to_minor(raw: str, minor: int) -> None:
    assert amount_to_minor(raw) == minor


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("EUR 4.10", [(410, "EUR")], id="code-before-amount"),
        pytest.param("4,10 EUR", [(410, "EUR")], id="code-after-amount"),
        pytest.param("4.10€", [(410, "EUR")], id="euro-symbol-after"),
        pytest.param("€4.10", [(410, "EUR")], id="euro-symbol-before"),
        pytest.param("$4", [(400, "USD")], id="dollar-symbol"),
        pytest.param("US$ 4.20", [(420, "USD")], id="us-dollar-prefix"),
        pytest.param("¥33", [(3300, "CNY")], id="yen-symbol-is-cny"),
        pytest.param("33元", [(3300, "CNY")], id="yuan-character-after"),
        pytest.param("RMB 33", [(3300, "CNY")], id="rmb-code-before"),
        pytest.param("£3.20", [(320, "GBP")], id="pound-symbol"),
        pytest.param("JPY 500", [(50000, "JPY")], id="jpy-code-two-decimals"),
        pytest.param("EUR 1.200,50", [(120050, "EUR")], id="eu-thousands-after-code"),
        pytest.param(
            "EUR 4.10, then 4.00 EUR",
            [(410, "EUR"), (400, "EUR")],
            id="multiple-prices-order-preserved",
        ),
        pytest.param(
            "¥33 or 4,10 EUR",
            [(3300, "CNY"), (410, "EUR")],
            id="multiple-prices-mixed-currencies",
        ),
        pytest.param("5000 units", [], id="bare-number-units"),
        pytest.param("we need 300 boxes", [], id="bare-number-boxes"),
        pytest.param("round 2", [], id="bare-number-round"),
        pytest.param("net 30", [], id="bare-number-net-terms"),
    ],
)
def test_find_prices(text: str, expected: list[tuple[int, str]]) -> None:
    assert [(p.minor, p.currency) for p in find_prices(text)] == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("5000 units", [5000], id="en-units"),
        pytest.param("5.000 uds", [5000], id="es-uds-dot-thousands"),
        pytest.param("5,000 pcs", [5000], id="en-pcs-comma-thousands"),
        pytest.param("2k units", [2000], id="en-k-suffix"),
        pytest.param("300 cajas", [300], id="es-cajas"),
        pytest.param("1000件", [1000], id="zh-jian"),
        pytest.param("EUR 4.10", [], id="price-is-not-quantity"),
    ],
)
def test_find_quantities(text: str, expected: list[int]) -> None:
    assert find_quantities(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("we can prepay 30%", frozenset({Counterpart.PREPAYMENT}), id="en-prepay"),
        pytest.param(
            "pago por adelantado", frozenset({Counterpart.PREPAYMENT}), id="es-pago-adelantado"
        ),
        pytest.param("预付50%", frozenset({Counterpart.PREPAYMENT}), id="zh-yufu"),
        pytest.param(
            "framework agreement",
            frozenset({Counterpart.FRAMEWORK_CONTRACT}),
            id="en-framework-agreement",
        ),
        pytest.param(
            "contrato marco", frozenset({Counterpart.FRAMEWORK_CONTRACT}), id="es-contrato-marco"
        ),
        pytest.param("net 60", frozenset({Counterpart.PAYMENT_TERMS}), id="en-net-60"),
        pytest.param(
            "pago a 90 días", frozenset({Counterpart.PAYMENT_TERMS}), id="es-pago-90-dias"
        ),
        pytest.param(
            "letter of credit", frozenset({Counterpart.GUARANTEE}), id="en-letter-of-credit"
        ),
        pytest.param(
            "garantía bancaria", frozenset({Counterpart.GUARANTEE}), id="es-garantia-bancaria"
        ),
        pytest.param("penalty clause", frozenset({Counterpart.PENALTY}), id="en-penalty-clause"),
        pytest.param("penalización", frozenset({Counterpart.PENALTY}), id="es-penalizacion"),
        pytest.param(
            "Thanks, the datasheet is attached.",
            frozenset(),
            id="neutral-sentence",
        ),
    ],
)
def test_find_counterparts(text: str, expected: frozenset[Counterpart]) -> None:
    assert find_counterparts(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("We accept your offer", True, id="en-we-accept"),
        pytest.param("It's a deal", True, id="en-its-a-deal"),
        pytest.param("We will place the order today", True, id="en-place-the-order"),
        pytest.param("Trato hecho", True, id="es-trato-hecho"),
        pytest.param("Aceptamos", True, id="es-aceptamos"),
        pytest.param("成交", True, id="zh-chengjiao"),
        pytest.param("Could you accept EUR 4.10?", False, id="en-question-accept"),
        pytest.param("We would like to understand your terms", False, id="en-understand-terms"),
        pytest.param(
            "If acceptable to you, please confirm in writing",
            False,
            id="en-conditional-confirm",
        ),
    ],
)
def test_has_binding_commitment(text: str, expected: bool) -> None:
    assert has_binding_commitment(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("buyer@example.com", True, id="email"),
        pytest.param("+34 600 123 456", True, id="phone-international"),
        pytest.param("www.example.com", True, id="url"),
        pytest.param("add me on WhatsApp", True, id="whatsapp"),
        pytest.param("加我微信", True, id="zh-wechat"),
        pytest.param("Please reply here on the platform", False, id="on-platform-reply"),
    ],
)
def test_has_off_platform_contact(text: str, expected: bool) -> None:
    assert has_off_platform_contact(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("pay by direct bank transfer", True, id="en-direct-bank-transfer"),
        pytest.param("let's keep it outside the platform", True, id="en-outside-platform"),
        pytest.param("Western Union", True, id="en-western-union"),
        pytest.param("pago fuera de la plataforma", True, id="es-fuera-de-la-plataforma"),
        pytest.param("pay through the platform escrow", False, id="en-escrow-on-platform"),
    ],
)
def test_has_off_platform_payment(text: str, expected: bool) -> None:
    assert has_off_platform_payment(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("ES91 2100 0418 4502 0005 1332", True, id="iban"),
        pytest.param("4111 1111 1111 1111", True, id="luhn-valid-card"),
        pytest.param("4111 1111 1111 1112", False, id="luhn-invalid-16-digits"),
        pytest.param("12345678Z", True, id="es-nif"),
        pytest.param("Thanks for the quick reply, see you tomorrow.", False, id="plain-text"),
    ],
)
def test_has_sensitive_data(text: str, expected: bool) -> None:
    assert has_sensitive_data(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("send your bank account details", True, id="en-bank-account-details"),
        pytest.param("what is your tax ID", True, id="en-tax-id"),
        pytest.param("envíame tu contraseña", True, id="es-contrasena"),
        pytest.param("请提供护照", True, id="zh-passport"),
        pytest.param("send the product datasheet", False, id="en-datasheet"),
    ],
)
def test_asks_for_sensitive_data(text: str, expected: bool) -> None:
    assert asks_for_sensitive_data(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("I can do EUR 4.00 if you close today", True, id="en-if-you-close-today"),
        pytest.param("only valid today", True, id="en-only-valid-today"),
        pytest.param("offer expires in 1 hour", True, id="en-offer-expires"),
        pytest.param("si cierras hoy", True, id="es-si-cierras-hoy"),
        pytest.param("今天下单", True, id="zh-order-today"),
        pytest.param("we can ship next week", False, id="no-pressure"),
    ],
)
def test_has_closing_pressure(text: str, expected: bool) -> None:
    assert has_closing_pressure(text) is expected
