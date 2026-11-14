from decimal import Decimal
import pytest
from helseark.serialization import encode_json, decode_json, hash_bytes
from helseark.contracts import ArchiveError


def test_decimal_scale_and_long_precision():
    raw = b'{"a":1.20,"b":0.123456789012345678901234567890123456789}'
    value = decode_json(raw)
    assert value["a"].as_tuple().exponent == -2
    assert value["b"] == Decimal("0.123456789012345678901234567890123456789")
    assert b'1.20' in encode_json(value)
    assert decode_json(encode_json(value)) == value


def test_determinism_and_content():
    left = {"z": [Decimal("1.20"), "é\n"], "a": {"x": True}}
    right = {"a": {"x": True}, "z": [Decimal("1.20"), "é\n"]}
    assert hash_bytes(encode_json(left)) == hash_bytes(encode_json(right))
    assert hash_bytes(encode_json(left)) != hash_bytes(encode_json({"z": list(reversed(left["z"])), "a": left["a"]}))
    assert encode_json({"b": 2, "a": 1}) == b'{\n  "a": 1,\n  "b": 2\n}\n'


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}', b'NaN', b'Infinity', b'\xff', b'"\\ud800"',
    b'[' * 65 + b'0' + b']' * 65, b'\xef\xbb\xbf{}',
])
def test_invalid_json(raw):
    with pytest.raises(ArchiveError):
        decode_json(raw)


@pytest.mark.parametrize("token", ["1e999999999", "1e129", "1e-129", "9"*129, "0."+"0"*1024+"1"])
def test_numeric_limits_before_expansion(token):
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        decode_json(token.encode())


@pytest.mark.parametrize("value", [float("nan"), 1.2, Decimal("1e999999999"), Decimal("NaN"), "\ud800", {1: "x"}])
def test_invalid_python_values(value):
    with pytest.raises(ArchiveError):
        encode_json(value)


def test_fractional_coefficient_boundary_and_effective_exponent():
    # Leading zero in 0.xxx is not part of the Decimal coefficient.
    number = Decimal("0." + "1" * 128)
    assert decode_json(encode_json(number)) == number
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        decode_json(b"0.1e-128")


def test_fixed_form_output_also_obeys_numeric_limits():
    # Expansion must never produce bytes that this same decoder rejects.
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        encode_json(Decimal("1e128"))
    assert decode_json(encode_json(Decimal("1e127"))) == Decimal("1e127")
