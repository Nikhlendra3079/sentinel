import uuid
from types import SimpleNamespace

import pytest

from app.limiter.policy_resolution import policy_matches, resolve_policy


def policy(pattern: str, *, active: bool = True):
    return SimpleNamespace(endpoint_pattern=pattern, is_active=active, id=uuid.uuid4())


def test_exact_match_beats_prefix_and_catch_all():
    fallback, prefix, exact = policy("*"), policy("/v1/*"), policy("/v1/users")
    assert resolve_policy([fallback, prefix, exact], "/v1/users") is exact


def test_longest_prefix_wins():
    broad, narrow = policy("/v1/*"), policy("/v1/admin/*")
    assert resolve_policy([broad, narrow], "/v1/admin/keys") is narrow


def test_catch_all_used_when_no_more_specific_match():
    fallback = policy("*")
    assert resolve_policy([fallback, policy("/v2/*")], "/v1/users") is fallback


def test_inactive_policy_is_ignored():
    assert resolve_policy([policy("/v1/*", active=False)], "/v1/users") is None


def test_no_match_returns_none():
    assert resolve_policy([policy("/v2/*")], "/v1/users") is None


def test_ambiguous_duplicate_specificity_raises():
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_policy([policy("/v1/*"), policy("/v1/*")], "/v1/users")


@pytest.mark.parametrize(("pattern", "path", "expected"), [
    ("*", "/anything", True),
    ("/v1/*", "/v1", True),
    ("/v1/*", "/v1/users", True),
    ("/v1/*", "/v10/users", False),
    ("/v1/users", "/v1/users/123", False),
])
def test_policy_matches(pattern, path, expected):
    assert policy_matches(pattern, path) is expected
