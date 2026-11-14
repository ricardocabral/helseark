from decimal import Decimal
import pytest
from helseark.serialization import encode_json, decode_json, decode_canonical_json, hash_bytes
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


@pytest.mark.parametrize("token", [
    "1e128", "0e128", "0.1e-128", "9" * 128 + "e128",
    "0." + "1" * 128 + "e-128", "1e127", "1e-128", "-0.00",
    "1e" + "0" * 1021 + "1", "0." + "0" * 510,
    "-0." + "0" * 509, "0." + "0" * 509 + "1",
])
def test_original_source_acceptance_and_canonical_closure(token):
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 2
        value = decode_json(token.encode())
        encoded = encode_json(value)
        reread = decode_canonical_json(encoded)
        assert reread == Decimal(token)
        assert b"e" not in encoded.lower()
        assert encode_json(reread) == encoded
        assert hash_bytes(encode_json(reread)) == hash_bytes(encoded)
        if isinstance(value, Decimal) and value.as_tuple().exponent < 0:
            assert reread.as_tuple() == value.as_tuple()


@pytest.mark.parametrize("token", [
    "0." + "0" * 511, "-0." + "0" * 510,
    "0." + "0" * 382 + "1e-128", "1e" + "0" * 1022 + "1",
    "0e129", "0e-129", "0e" + "9" * 1000,
])
def test_source_rejects_each_independent_limit(token):
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        decode_json(token.encode())


def test_distinct_source_and_canonical_coefficient_bounds():
    token = b"1" + b"0" * 128
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        decode_json(token)
    assert decode_canonical_json(token) == 10 ** 128
    assert encode_json(decode_canonical_json(token)) == token + b"\n"


@pytest.mark.parametrize("token", [
    "9" * 129, "1" + "0" * 256, "1" * 129 + "0" * 128,
    "0." + "1" * 129, "0." + "0" * 511,
    "-0." + "0" * 510,
])
def test_canonical_rejects_values_without_bounded_source_preimage(token):
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        decode_canonical_json(token.encode())
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        encode_json(Decimal(token))


@pytest.mark.parametrize("token", ["1e128", "1e999999999", "0e128", "1e-129"])
def test_canonical_decoder_requires_fixed_notation(token):
    with pytest.raises(ArchiveError, match="INVALID_JSON"):
        decode_canonical_json(token.encode())


@pytest.mark.parametrize("reader", [decode_json, decode_canonical_json])
@pytest.mark.parametrize("raw,code", [
    (b'{"private":0,"private":1}', "DUPLICATE_KEY"),
    (b'"\\ud800"', "INVALID_JSON"), (b"NaN", "INVALID_JSON"),
    (b"[" * 65 + b"0" + b"]" * 65, "DEPTH_LIMIT"),
    (b"\xff", "INVALID_JSON"), (b"\xef\xbb\xbf{}", "INVALID_JSON"),
])
def test_both_readers_preserve_safe_errors(reader, raw, code):
    with pytest.raises(ArchiveError) as error:
        reader(raw)
    assert error.value.code == code
    assert "private" not in str(error.value)


def test_integer_zero_normalization_preserves_canonical_idempotence():
    for token in ["-0", "-0e128", "0e128"]:
        encoded = encode_json(decode_json(token.encode()))
        assert encoded == b"0\n"
        assert encode_json(decode_canonical_json(encoded)) == encoded


def test_systematic_source_boundary_matrix():
    # Independent oracle is Decimal fixed formatting and tuple scale, at low precision.
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 2
        for coefficient in ["0", "1", "9" * 128]:
            for fraction in [0, 1, 128, 383, 510]:
                for exponent in [-128, -1, 0, 1, 128]:
                    for sign in ["", "-"]:
                        token = sign + ("0." + "0" * fraction + coefficient
                                        if fraction else coefficient) + "e" + str(exponent)
                        expected = Decimal(token)
                        fixed = format(expected, "f")
                        if len(fixed) > 512:
                            with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
                                decode_json(token.encode())
                            continue
                        value = decode_json(token.encode())
                        encoded = encode_json(value)
                        reread = decode_canonical_json(encoded)
                        assert reread == expected
                        if expected.as_tuple().exponent < 0:
                            assert reread.as_tuple() == expected.as_tuple()
                        assert encode_json(reread) == encoded


def test_external_malformed_json_stays_invalid_input():
    with pytest.raises(ArchiveError, match='INVALID_JSON'):
        decode_json(b'{"PRIVATE RECORD":')


@pytest.mark.parametrize("reader", [decode_json, decode_canonical_json])
def test_both_readers_allow_depth_boundary_and_preserve_unicode(reader):
    raw = b"[" * 64 + '"é{}[]"'.encode() + b"]" * 64
    assert encode_json(reader(raw)).count("é".encode()) == 1


def test_python_representation_bounds_and_giant_integer_short_circuit():
    # The encoder validates values, while source parsing bounds explicit spelling.
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        decode_json(b"1e129")
    encoded = encode_json(Decimal("1e129"))
    assert encode_json(decode_canonical_json(encoded)) == encoded
    with pytest.raises(ArchiveError, match="NUMERIC_LIMIT"):
        encode_json(1 << 100_000)
    # Positive integer zero scale is discarded without an exponent expansion.
    assert encode_json(Decimal("-0e999999999")) == b"0\n"
