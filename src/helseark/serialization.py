"""helseark-json-1: bounded exact numbers and deterministic UTF-8 bytes."""
import hashlib
import json
import re
from decimal import Decimal
from .contracts import ArchiveError, JsonValue, Sha256

_NUMBER = re.compile(r"(-?)(0|[1-9][0-9]*)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?\Z")


def _number(token: str) -> int | Decimal:
    # Bound the exponent's text before int() or Decimal() can allocate work.
    if len(token) > 1024:
        raise ArchiveError("NUMERIC_LIMIT", "Number token exceeds archive limits.")
    match = _NUMBER.fullmatch(token)
    if not match:
        raise ArchiveError("INVALID_JSON", "Invalid number.")
    sign, whole, fraction, exponent = match.groups()
    exponent_text = (exponent or "0").lstrip("+-").lstrip("0") or "0"
    if len(exponent_text) > 3:
        raise ArchiveError("NUMERIC_LIMIT", "Number exponent exceeds archive limits.")
    exp = int(exponent or "0")
    coefficient = whole + (fraction or "")
    scale = exp - len(fraction or "")
    digits = len(coefficient.lstrip("0") or "0")
    if digits > 128 or abs(exp) > 128:
        raise ArchiveError("NUMERIC_LIMIT", "Number exceeds archive limits.")
    if _fixed_size(sign, digits, scale, not coefficient.strip("0")) > 512:
        raise ArchiveError("NUMERIC_LIMIT", "Expanded number exceeds archive limits.")
    return Decimal(token) if fraction is not None or exponent is not None else int(token)


def _fixed_size(sign, digits, scale, zero):
    if scale >= 0:
        return len(sign) + (1 if zero else digits + scale)
    return len(sign) + max(digits + scale, 1) + 1 - scale


def _canonical_number(token: str) -> int | Decimal:
    # Fixed tokens must have a bounded source preimage, not merely fit in memory.
    if len(token) > 512:
        raise ArchiveError("NUMERIC_LIMIT", "Canonical number exceeds archive limits.")
    match = _NUMBER.fullmatch(token)
    if not match or match[4] is not None:
        raise ArchiveError("INVALID_JSON", "Canonical numbers require fixed notation.")
    _, whole, fraction, _ = match.groups()
    coefficient = (whole + (fraction or "")).lstrip("0") or "0"
    if fraction is not None:
        allowed = len(coefficient) <= 128
    else:
        # At most 128 zeroes can have been appended by a source exponent.
        removed = min(len(coefficient) - len(coefficient.rstrip("0")), 128)
        allowed = len(coefficient) - removed <= 128
    if not allowed:
        raise ArchiveError("NUMERIC_LIMIT", "Canonical coefficient exceeds archive limits.")
    return Decimal(token) if fraction is not None else int(token)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArchiveError("DUPLICATE_KEY", "Duplicate JSON object key.")
        value[key] = item
    return value


def _reject_constant(_):
    raise ArchiveError("INVALID_JSON", "Non-finite numbers are forbidden.")


def _check_depth_text(text: str):
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 64:
                raise ArchiveError("DEPTH_LIMIT", "JSON nesting exceeds 64 containers.")
        elif char in "]}":
            depth -= 1


def decode_json(data: bytes) -> JsonValue:
    """Read source JSON with the original independent token limits."""
    return _decode_json(data, _number)


def decode_canonical_json(data: bytes) -> JsonValue:
    """Read retained JSON: bounded fixed numbers with a permitted source preimage.

    This validates numeric representation, not whitespace/key canonicality.
    encode_json(decode_canonical_json(encode_json(value))) is byte-stable.
    """
    return _decode_json(data, _canonical_number)


def _decode_json(data: bytes, number) -> JsonValue:
    try:
        text = data.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise ValueError
        _check_depth_text(text)
        value = json.loads(text, parse_float=number, parse_int=number,
                           parse_constant=_reject_constant, object_pairs_hook=_pairs)
        # Also checks escaped lone surrogates, not just UTF-8 input bytes.
        encode_json(value)
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise ArchiveError("INVALID_JSON", "Invalid UTF-8 JSON.") from None


def encode_json(value: JsonValue) -> bytes:
    """Encode the bounded canonical value domain, including source expansions."""
    def render(item, depth):
        if item is None:
            return "null"
        if type(item) is bool:
            return "true" if item else "false"
        if type(item) is int:
            # A 256-digit integer has at most 851 bits; avoid giant str(int).
            if item.bit_length() > 851:
                raise ArchiveError("NUMERIC_LIMIT", "Integer exceeds archive limits.")
            token = str(item)
            _canonical_number(token)
            return token
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ArchiveError("NUMERIC_LIMIT", "Non-finite decimal.")
            sign, digits, scale = item.as_tuple()
            # Size checks precede fixed expansion, even for giant exponents.
            if len(digits) > 512 or _fixed_size("-" if sign else "", len(digits),
                                               scale, item.is_zero()) > 512:
                raise ArchiveError("NUMERIC_LIMIT", "Expanded number exceeds archive limits.")
            token = "0" if item.is_zero() and scale >= 0 else format(item, "f")
            _canonical_number(token)
            return token
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
            return json.dumps(item, ensure_ascii=False)
        if type(item) not in (list, dict):
            raise ArchiveError("INVALID_JSON", "Unsupported JSON value; floats are forbidden.")
        if depth >= 64:
            raise ArchiveError("DEPTH_LIMIT", "JSON nesting exceeds 64 containers.")
        if isinstance(item, dict) and any(not isinstance(k, str) for k in item):
            raise ArchiveError("INVALID_JSON", "Object keys must be strings.")
        if not item:
            return "{}" if isinstance(item, dict) else "[]"
        pad = "  " * (depth + 1)
        if isinstance(item, dict):
            entries = [render(k, depth + 1) + ": " + render(item[k], depth + 1) for k in sorted(item)]
            left, right = "{", "}"
        else:
            entries = [render(v, depth + 1) for v in item]
            left, right = "[", "]"
        return left + "\n" + pad + (",\n" + pad).join(entries) + "\n" + "  " * depth + right
    try:
        return (render(value, 0) + "\n").encode("utf-8")
    except (UnicodeError, ValueError, RecursionError):
        raise ArchiveError("INVALID_JSON", "Invalid JSON value.") from None


def hash_bytes(data: bytes) -> Sha256:
    return hashlib.sha256(data).hexdigest()
