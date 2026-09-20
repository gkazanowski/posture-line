"""Geometry ported from HTML; intentionally without aspect ratio correction.

This module can be refined later without changing the GUI or camera code.
"""
from math import atan2, degrees, floor
from types import SimpleNamespace

INDICES = {"left": (15, 13, 11, 23, 25, 27), "right": (16, 14, 12, 24, 26, 28)}


def angle(a, b, c):
    ax, ay = a.x - b.x, a.y - b.y
    bx, by = c.x - b.x, c.y - b.y
    # Match the original JavaScript Math.round behavior for nonnegative angles.
    return floor(degrees(atan2(abs(ax * by - ay * bx), ax * bx + ay * by)) + 0.5)


def analyze(landmarks, side):
    """Return (chain, measurements), or None if the selected side is not visible."""
    if not landmarks or len(landmarks) <= max(INDICES[side]):
        return None
    chain = [landmarks[i] for i in INDICES[side]]
    if any(p.visibility is None or p.visibility < 0.5 for p in chain):
        return None
    hand, elbow, shoulder, hip, knee, foot = chain
    vertical = SimpleNamespace(x=hip.x, y=hip.y - 0.2)
    return chain, {
        "elbow": angle(hand, elbow, shoulder),
        "knee": angle(hip, knee, foot),
        "torso": angle(vertical, hip, shoulder),
    }
