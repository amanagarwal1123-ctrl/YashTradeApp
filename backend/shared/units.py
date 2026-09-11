"""Non-destructive compatibility adapters. No quantity or pricing basis conversion."""
import re
from decimal import Decimal, InvalidOperation


def weight_text(value):
    if value in (None, ""):
        return value
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:[-–]\s*(\d+(?:\.\d+)?))?\s*(?:g|gm|gms|gram|grams)\s*(?:(?:per\s+|/\s*)(pair|piece))?\s*", str(value), re.I)
    if not match:
        raise ValueError("approx_weight: use grams, optionally per pair/piece; ambiguous weights need review")
    first, last, basis = match.groups()
    if Decimal(first) <= 0 or last and Decimal(last) < Decimal(first):
        raise ValueError("approx_weight: positive ascending range required")
    return first + (f"-{last}" if last else "") + " g" + (f" per {basis.lower()}" if basis else "")


def labour_value(value):
    """The old labour_kg field's bare numbers mean INR/kg; labelled units win."""
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        if set(value) != {"currency", "amount", "basis"} or value["currency"] != "INR" or value["basis"] not in {"kg", "10g", "piece"}:
            raise ValueError("labour: specify INR, amount and kg/10g/piece basis")
        amount, basis = str(value["amount"]), value["basis"]
    else:
        match = re.fullmatch(r"\s*(?:(?:INR|₹|Rs\.?)\s*)?(\d+(?:\.\d+)?)\s*(?:(?:/|per\s+)\s*(kg|10\s*g|piece|pc))?\s*", str(value), re.I)
        if not match:
            raise ValueError("labour: ambiguous amount/unit; use INR 850/kg, INR 50/10g or INR 20/piece")
        amount, basis = match.groups()
        basis = (basis or "kg").replace(" ", "").lower()
        basis = "piece" if basis == "pc" else basis
    try:
        number = Decimal(amount)
        if not number.is_finite() or number < 0:
            raise InvalidOperation()
    except InvalidOperation as exc:
        raise ValueError("labour: finite non-negative amount required") from exc
    return {"currency": "INR", "amount": format(number, "f"), "basis": basis}


def slab_view(doc):
    result = dict(doc)
    result.setdefault("version", 0)
    try:
        labour = labour_value(doc.get("labour", doc.get("labour_kg")))
        result["labour"] = labour
        result["labour_display"] = f"INR {labour['amount']}/{labour['basis']}" if labour else "—"
        result["unit_review_required"] = False
    except ValueError:
        result.update(labour=None, labour_display=str(doc.get("labour_kg", "")), unit_review_required=True)
    return result