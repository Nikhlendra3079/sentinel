from app.core.security import (
    extract_public_prefix,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


def test_generated_api_key_has_expected_format_and_hash() -> None:
    generated = generate_api_key()

    assert generated.full_key.startswith("sk_live_")
    assert extract_public_prefix(generated.full_key) == generated.public_prefix
    assert generated.key_hash == hash_api_key(generated.full_key)
    assert verify_api_key(generated.full_key, generated.key_hash)


def test_different_api_keys_have_different_values() -> None:
    first = generate_api_key()
    second = generate_api_key()

    assert first.full_key != second.full_key
    assert first.public_prefix != second.public_prefix
    assert first.key_hash != second.key_hash


def test_invalid_key_formats_are_rejected() -> None:
    assert extract_public_prefix("") is None
    assert extract_public_prefix("sk_test_abc_secret") is None
    assert extract_public_prefix("sk_live_short_secret") is None
    assert extract_public_prefix("sk_live_zzzzzzzzzzzzzzzz_secret") is None


def test_wrong_secret_does_not_verify() -> None:
    generated = generate_api_key()
    assert not verify_api_key(generated.full_key + "wrong", generated.key_hash)


def test_secret_may_contain_underscores() -> None:
    generated = generate_api_key()
    # The parser splits only the first three separators; URL-safe secrets may
    # themselves contain underscores.
    assert extract_public_prefix(generated.full_key) == generated.public_prefix
