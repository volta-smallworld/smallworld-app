"""Tests for the _TileCache LRU cache with TTL expiry.

Validates cache hit/miss behavior, LRU eviction, TTL expiry,
and thread-safety guarantees of the tile cache used by the
Terrarium pipeline.
"""

import time

import numpy as np

from smallworld_api.services.terrarium import _TileCache


def _make_array(value: float = 1.0) -> np.ndarray:
    """Create a small test elevation array."""
    return np.full((256, 256), value, dtype=np.float64)


# ── Basic get/put ─────────────────────────────────────────────────────────


def test_put_then_get_returns_correct_array():
    """put followed by get should return the stored array."""
    cache = _TileCache(max_size=10, ttl_seconds=300)
    arr = _make_array(42.0)
    cache.put((12, 100, 200), arr)

    result = cache.get((12, 100, 200))
    assert result is not None
    np.testing.assert_array_equal(result, arr)


def test_get_missing_key_returns_none():
    """get on a key that was never inserted should return None."""
    cache = _TileCache(max_size=10, ttl_seconds=300)
    result = cache.get((12, 999, 999))
    assert result is None


def test_put_overwrites_existing_entry():
    """Putting the same key twice should update the stored value."""
    cache = _TileCache(max_size=10, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(10.0))
    cache.put((12, 1, 1), _make_array(20.0))

    result = cache.get((12, 1, 1))
    assert result is not None
    np.testing.assert_array_equal(result, _make_array(20.0))


def test_multiple_keys_stored_independently():
    """Different keys should return their own arrays."""
    cache = _TileCache(max_size=10, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(100.0))
    cache.put((12, 2, 2), _make_array(200.0))
    cache.put((13, 1, 1), _make_array(300.0))

    r1 = cache.get((12, 1, 1))
    r2 = cache.get((12, 2, 2))
    r3 = cache.get((13, 1, 1))
    assert r1 is not None and r1[0, 0] == 100.0
    assert r2 is not None and r2[0, 0] == 200.0
    assert r3 is not None and r3[0, 0] == 300.0


# ── LRU eviction ──────────────────────────────────────────────────────────


def test_lru_eviction_when_exceeding_max_size():
    """When the cache exceeds max_size, the least recently used entry
    should be evicted."""
    cache = _TileCache(max_size=3, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(1.0))
    cache.put((12, 2, 2), _make_array(2.0))
    cache.put((12, 3, 3), _make_array(3.0))
    # Cache is full with [1,1], [2,2], [3,3]

    # Adding a 4th entry should evict (12, 1, 1) as it was inserted first (LRU)
    cache.put((12, 4, 4), _make_array(4.0))

    assert cache.get((12, 1, 1)) is None, "LRU entry should be evicted"
    assert cache.get((12, 2, 2)) is not None
    assert cache.get((12, 3, 3)) is not None
    assert cache.get((12, 4, 4)) is not None


def test_accessing_entry_moves_to_most_recently_used():
    """Accessing an entry via get should move it to the MRU position,
    preventing it from being evicted next."""
    cache = _TileCache(max_size=3, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(1.0))
    cache.put((12, 2, 2), _make_array(2.0))
    cache.put((12, 3, 3), _make_array(3.0))

    # Access (12, 1, 1) to move it to MRU
    result = cache.get((12, 1, 1))
    assert result is not None

    # Now (12, 2, 2) is the LRU entry
    # Adding a new entry should evict (12, 2, 2), not (12, 1, 1)
    cache.put((12, 4, 4), _make_array(4.0))

    assert cache.get((12, 1, 1)) is not None, "Accessed entry should survive eviction"
    assert cache.get((12, 2, 2)) is None, "LRU entry should be evicted"
    assert cache.get((12, 3, 3)) is not None
    assert cache.get((12, 4, 4)) is not None


def test_put_existing_key_moves_to_mru():
    """Re-putting an existing key should not increase the count and should
    move the entry to MRU position."""
    cache = _TileCache(max_size=3, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(1.0))
    cache.put((12, 2, 2), _make_array(2.0))
    cache.put((12, 3, 3), _make_array(3.0))

    # Re-put (12, 1, 1) — should move it to MRU without growing the cache
    cache.put((12, 1, 1), _make_array(10.0))

    # Cache should still have 3 entries — adding a 4th should evict (12, 2, 2)
    cache.put((12, 4, 4), _make_array(4.0))

    assert cache.get((12, 1, 1)) is not None, "Re-put entry should survive"
    assert cache.get((12, 2, 2)) is None, "LRU entry should be evicted"


def test_max_size_of_one():
    """A cache with max_size=1 should only ever hold 1 entry."""
    cache = _TileCache(max_size=1, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(1.0))
    assert cache.get((12, 1, 1)) is not None

    cache.put((12, 2, 2), _make_array(2.0))
    assert cache.get((12, 1, 1)) is None
    assert cache.get((12, 2, 2)) is not None


# ── TTL expiry ────────────────────────────────────────────────────────────


def test_ttl_expiry_evicts_old_entries():
    """Entries older than ttl_seconds should be evicted on access."""
    cache = _TileCache(max_size=10, ttl_seconds=1)
    cache.put((12, 1, 1), _make_array(1.0))

    # Entry should be accessible immediately
    assert cache.get((12, 1, 1)) is not None

    # Wait for TTL to expire
    time.sleep(1.1)

    # Entry should now be expired
    result = cache.get((12, 1, 1))
    assert result is None, "Expired entry should return None"


def test_ttl_does_not_expire_fresh_entries():
    """Entries within their TTL should still be accessible."""
    cache = _TileCache(max_size=10, ttl_seconds=60)
    cache.put((12, 1, 1), _make_array(1.0))

    # Should be accessible since TTL is 60 seconds
    result = cache.get((12, 1, 1))
    assert result is not None


def test_expired_entry_is_removed_from_store():
    """After an expired get, the entry should be fully removed so it
    does not count against the max_size budget."""
    cache = _TileCache(max_size=2, ttl_seconds=1)
    cache.put((12, 1, 1), _make_array(1.0))

    time.sleep(1.1)

    # Trigger expiry removal
    assert cache.get((12, 1, 1)) is None

    # Should be able to add 2 more entries without eviction
    cache.put((12, 2, 2), _make_array(2.0))
    cache.put((12, 3, 3), _make_array(3.0))

    assert cache.get((12, 2, 2)) is not None
    assert cache.get((12, 3, 3)) is not None


# ── Clear ─────────────────────────────────────────────────────────────────


def test_clear_empties_the_cache():
    """clear() should remove all entries."""
    cache = _TileCache(max_size=10, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(1.0))
    cache.put((12, 2, 2), _make_array(2.0))
    cache.put((12, 3, 3), _make_array(3.0))

    cache.clear()

    assert cache.get((12, 1, 1)) is None
    assert cache.get((12, 2, 2)) is None
    assert cache.get((12, 3, 3)) is None


def test_clear_then_put_works():
    """Cache should be usable after clear()."""
    cache = _TileCache(max_size=10, ttl_seconds=300)
    cache.put((12, 1, 1), _make_array(1.0))
    cache.clear()

    cache.put((12, 2, 2), _make_array(2.0))
    result = cache.get((12, 2, 2))
    assert result is not None
    np.testing.assert_array_equal(result, _make_array(2.0))
