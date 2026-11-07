"""UUIDv7 generation (RFC 9562): time-ordered ids with good index locality."""

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last = 0


def _compose(ts_ms: int, rand: int) -> int:
    rand_a = (rand >> 62) & 0xFFF  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    return ((ts_ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b


def uuid7() -> uuid.UUID:
    """Return a new UUIDv7, strictly increasing within this process.

    Layout: 48-bit Unix ms timestamp, version 7, 12 + 62 random bits, variant 10. When two
    ids fall in the same millisecond the random part is incremented instead (RFC 9562
    §6.2 method 2), so ids created in sequence also sort in creation order.
    """
    global _last
    value = _compose(time.time_ns() // 1_000_000, int.from_bytes(os.urandom(10), "big"))
    with _lock:
        if value <= _last:
            # Increment the 74 random bits, skipping over the fixed version/variant bits.
            rand = ((_last >> 64) & 0xFFF) << 62 | (_last & ((1 << 62) - 1))
            value = _compose(_last >> 80, rand + 1)
            if value <= _last:  # random part overflowed: move to the next millisecond
                value = _compose((_last >> 80) + 1, 0)
        _last = value
    return uuid.UUID(int=value)
