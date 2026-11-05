"""
The elbow (knee) of a curve, by the Kneedle rule (Satopaa et al. 2011): with both axes scaled
to [0, 1], the knee is the point farthest from the straight line through the first and the
last point. Used by every parameter choice (explore/r12_joint.py, r12_params.py, r12_f9.py).

find() first checks that the curve has a knee at all:
  flat      the curve changes by less than FLAT of its size: the parameter does nothing
  peak      the curve turns back: a point inside the range lies above both ends by more than
  valley    PEAK of the curve's spread (below both ends: valley). The knee is then looked for
            on the part of the curve up to that point (the part where it first moves): kind
            "knee before the peak/valley". If that part is too short (under 4 points) or has no
            knee, the index is the turning point itself (kind peak or valley); for a curve where
            lower is better (the reversal share of the slot length) the lowest point is the
            best value
  straight  the one-direction fit is at most STRAIGHT from the chord: no bend to pick
  edge      the knee falls on the first or last tested value: none inside the range
  knee      a proper knee
The knee is taken on the one-direction (isotonic) fit of the curve, so noise after the bend
does not move it.
"""
import numpy as np

FLAT, PEAK, STRAIGHT = 0.10, 0.20, 0.10


def knee(x, y):
    """Index of the knee of the curve (x, y), on a linear axis."""
    return int(np.argmax(_dist(x, y)))


def _dist(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    xn = (x - x.min()) / (x.max() - x.min())
    yn = (y - y.min()) / (y.max() - y.min())
    dx, dy = xn[-1] - xn[0], yn[-1] - yn[0]
    return np.abs(dy * (xn - xn[0]) - dx * (yn - yn[0])) / np.hypot(dx, dy)


def monotone(y, up):
    """Least-squares fit of y that only rises (up) or only falls (pool adjacent violators)."""
    v = list(np.asarray(y, float) * (1 if up else -1))
    blocks = []                                        # [mean, size]
    for a in v:
        blocks.append([a, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            (m1, n1), (m2, n2) = blocks.pop(-2), blocks.pop(-1)
            blocks.append([(m1 * n1 + m2 * n2) / (n1 + n2), n1 + n2])
    fit = np.concatenate([[m] * n for m, n in blocks])
    return fit * (1 if up else -1)


def find(x, y):
    """(index, kind) of the curve's knee; kind: knee, knee before the peak/valley, flat, peak, valley,
    straight or edge (see above)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    span = np.ptp(y)
    if span < FLAT * np.abs(y).max():
        return int(np.argmin(np.abs(y - y[0]))), "flat"
    for i, beyond, kind in ((np.argmax(y), y.max() - max(y[0], y[-1]), "peak"),
                            (np.argmin(y), min(y[0], y[-1]) - y.min(), "valley")):
        if beyond > PEAK * span:
            if i >= 3:
                j, part = find(x[:i + 1], y[:i + 1])
                if part == "knee":
                    return j, f"knee before the {kind}"
            return int(i), kind
    fit = monotone(y, up=y[-1] > y[0])
    if np.ptp(fit) == 0:
        return 0, "flat"
    d = _dist(x, fit)
    i = int(np.argmax(d))
    if d[i] <= STRAIGHT:
        return i, "straight"
    if i in (0, len(x) - 1):
        return i, "edge"
    return i, "knee"
