"""Notification texts (Spanish and English) and money formatting.

The text is built on the server because the push is shown by the OS, without running app
code. Each device's token stores the app language of that device.
"""

from __future__ import annotations

from typing import Literal

Locale = Literal["es", "en"]
SUPPORTED_LOCALES: tuple[Locale, ...] = ("es", "en")
DEFAULT_LOCALE: Locale = "es"

# Event kind -> template per locale. Placeholders: {actor}, {description}, {amount}.
TEMPLATES: dict[str, dict[Locale, str]] = {
    "expense_created": {
        "es": "{actor} agregó «{description}» · {amount}",
        "en": "{actor} added “{description}” · {amount}",
    },
    "expense_updated": {
        "es": "{actor} editó «{description}» · {amount}",
        "en": "{actor} edited “{description}” · {amount}",
    },
    "expense_deleted": {
        "es": "{actor} borró «{description}» · {amount}",
        "en": "{actor} deleted “{description}” · {amount}",
    },
    "payment_sent": {
        "es": "{actor} te envió {amount}. Confírmalo cuando lo recibas",
        "en": "{actor} sent you {amount}. Confirm it once you get it",
    },
    "payment_recorded": {
        "es": "{actor} registró que le pagaste {amount}",
        "en": "{actor} recorded your payment of {amount}",
    },
    "payment_confirmed": {
        "es": "{actor} confirmó tu pago de {amount}",
        "en": "{actor} confirmed your payment of {amount}",
    },
    "payment_disputed": {
        "es": "{actor} dice que no recibió tu pago de {amount}",
        "en": "{actor} says they did not get your payment of {amount}",
    },
    "payment_cancelled": {
        "es": "{actor} canceló el pago de {amount}",
        "en": "{actor} cancelled the payment of {amount}",
    },
    "member_joined": {
        "es": "{actor} se unió al grupo",
        "en": "{actor} joined the group",
    },
}

SOMEONE: dict[Locale, str] = {"es": "Alguien", "en": "Someone"}

MAX_DESCRIPTION = 60


def normalize_locale(value: str | None) -> Locale:
    """'es', 'es-ES', 'en-GB'... -> 'es' / 'en'; anything else falls back to Spanish."""
    prefix = (value or "").split("-")[0].lower()
    return "en" if prefix == "en" else DEFAULT_LOCALE


def format_amount(cents: int, locale: Locale) -> str:
    """EUR, the only currency today: '1.234,50 €' (es) / '€1,234.50' (en)."""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    grouped = f"{euros:,}"
    if locale == "es":
        return f"{sign}{grouped.replace(',', '.')},{rest:02d} €"
    return f"{sign}€{grouped}.{rest:02d}"


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_DESCRIPTION else text[: MAX_DESCRIPTION - 1] + "…"


def render_body(
    kind: str,
    locale: Locale,
    *,
    actor: str | None,
    description: str = "",
    amount_cents: int = 0,
) -> str:
    return TEMPLATES[kind][locale].format(
        actor=actor or SOMEONE[locale],
        description=_short(description),
        amount=format_amount(amount_cents, locale),
    )
