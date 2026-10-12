"""RFC 8785 JSON Canonicalization Scheme (P-001-07; digests of spec 002 are computed over these bytes).

Properties are sorted by UTF-16 code units, numbers use the ECMAScript ``Number::toString`` form, there is no
whitespace, and NaN or Infinity is an error (RFC 8785 sections 3.2.2 and 3.2.3).
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("NaN and Infinity cannot be canonicalised")
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    # shortest round-trip digits of repr(), re-expressed as ECMAScript digits d1..dk and exponent n (0.d1..dk * 10**n)
    _, digit_tuple, exponent = Decimal(repr(abs(value))).as_tuple()
    all_digits = "".join(map(str, digit_tuple)).rstrip("0") or "0"
    point = len(digit_tuple) + int(exponent)
    k, n = len(all_digits), point
    if k <= n <= 21:
        body = all_digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = all_digits[:n] + "." + all_digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + all_digits
    else:
        e = n - 1
        mant = all_digits[0] + ("." + all_digits[1:] if k > 1 else "")
        body = f"{mant}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


def _string(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("a string with a lone surrogate cannot be canonicalised") from None
    return json.dumps(value, ensure_ascii=False)


def _emit(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (int, float)):
        out.append(_number(float(value)))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _emit(item, out)
        out.append("]")
    elif isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("object keys must be strings")
        out.append("{")
        for index, key in enumerate(sorted(value, key=lambda k: k.encode("utf-16-be", "surrogatepass"))):
            if index:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _emit(value[key], out)
        out.append("}")
    else:
        raise ValueError(f"cannot canonicalise a value of type {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """The RFC 8785 canonical form of a JSON value, UTF-8 encoded."""
    out: list[str] = []
    _emit(value, out)
    return "".join(out).encode("utf-8")
