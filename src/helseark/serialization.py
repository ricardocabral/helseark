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
    # Apply limits to both the input and the required fixed-form representation.
    # Otherwise 1e128 would emit 129 coefficient digits that cannot be read back.
    if digits + max(scale, 0) > 128 or abs(exp) > 128 or abs(scale) > 128:
        raise ArchiveError("NUMERIC_LIMIT", "Number exceeds archive limits.")
    decimal_position = len(coefficient) + scale
    expanded = (len(sign) + max(decimal_position, 1)
                + (1 + max(-scale, 0) if scale < 0 else 0))
    if expanded > 512:
        raise ArchiveError("NUMERIC_LIMIT", "Expanded number exceeds archive limits.")
    return Decimal(token) if fraction is not None or exponent is not None else int(token)


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
    try:
        text = data.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise ValueError
        _check_depth_text(text)
        value = json.loads(text, parse_float=_number, parse_int=_number,
                           parse_constant=_reject_constant, object_pairs_hook=_pairs)
        # Also checks escaped lone surrogates, not just UTF-8 input bytes.
        encode_json(value)
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise ArchiveError("INVALID_JSON", "Invalid UTF-8 JSON.") from None


def encode_json(value: JsonValue) -> bytes:
    def render(item, depth):
        if item is None:
            return "null"
        if type(item) is bool:
            return "true" if item else "false"
        if type(item) is int:
            return str(_number(str(item)))
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ArchiveError("NUMERIC_LIMIT", "Non-finite decimal.")
            _number(str(item))
            return format(item, "f")
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
