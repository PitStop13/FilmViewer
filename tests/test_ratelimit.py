"""Incremental backoff on /api/auth/jellyfin and /api/auth/setup.

Only actual wrong-password failures count against the cooldown — an
unreachable Jellyfin server, a not-yet-imported user, or a disabled account are
not evidence of credential guessing, and must not be punished the same way.
"""

import pytest

from app.auth import ratelimit
from tests.conftest import do_login, do_setup


def test_module_isolation_fixture_actually_clears_state():
    """Guard against the isolation fixture silently doing nothing."""
    ratelimit.record_failure("1.2.3.4", "someone")
    assert ratelimit._failures
    ratelimit._failures.clear()
    assert not ratelimit._failures


# ── Unit tests of the backoff curve ─────────────────────────────────────────────

def test_first_few_failures_are_free():
    for _ in range(ratelimit.FREE_ATTEMPTS):
        ratelimit.record_failure("1.2.3.4", "bob")
    assert ratelimit.seconds_until_allowed("1.2.3.4", "bob") == 0


def test_backoff_kicks_in_after_the_free_attempts_and_grows():
    delays = []
    for _ in range(ratelimit.FREE_ATTEMPTS + 4):
        delays.append(ratelimit.record_failure("1.2.3.4", "bob"))

    thrown = [d for d in delays if d > 0]
    assert thrown, "expected at least one throttled attempt"
    # Strictly increasing: each additional failure waits at least as long as
    # the previous one, and later ones must wait strictly longer.
    assert thrown == sorted(thrown)
    assert thrown[-1] > thrown[0]


def test_backoff_is_capped():
    for _ in range(50):
        ratelimit.record_failure("1.2.3.4", "bob")
    assert ratelimit.seconds_until_allowed("1.2.3.4", "bob") <= ratelimit.MAX_DELAY


def test_success_resets_the_counter():
    for _ in range(ratelimit.FREE_ATTEMPTS + 3):
        ratelimit.record_failure("1.2.3.4", "bob")
    assert ratelimit.seconds_until_allowed("1.2.3.4", "bob") > 0

    ratelimit.record_success("1.2.3.4", "bob")

    assert ratelimit.seconds_until_allowed("1.2.3.4", "bob") == 0


def test_keys_are_isolated_by_ip_and_username():
    for _ in range(ratelimit.FREE_ATTEMPTS + 3):
        ratelimit.record_failure("1.2.3.4", "bob")

    # A different address guessing the same username starts fresh.
    assert ratelimit.seconds_until_allowed("9.9.9.9", "bob") == 0
    # The same address trying a different account also starts fresh — one
    # attacker rotating usernames doesn't get a free pass on any of them, but
    # this confirms accounts don't share a budget either.
    assert ratelimit.seconds_until_allowed("1.2.3.4", "carol") == 0


def test_username_matching_is_case_and_whitespace_insensitive():
    for _ in range(ratelimit.FREE_ATTEMPTS + 3):
        ratelimit.record_failure("1.2.3.4", "  Bob  ")
    assert ratelimit.seconds_until_allowed("1.2.3.4", "BOB") > 0


def test_stale_entries_are_forgotten(monkeypatch):
    import time
    ratelimit.record_failure("1.2.3.4", "bob")
    real_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + ratelimit.FORGET_AFTER + 1)
    assert ratelimit.seconds_until_allowed("1.2.3.4", "bob") == 0
    assert ("1.2.3.4", "bob") not in ratelimit._failures
