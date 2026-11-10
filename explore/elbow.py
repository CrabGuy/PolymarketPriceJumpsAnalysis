"""
The elbow (knee) of a curve, by Kneedle (Satopaa, Albrecht, Irwin and Raghavan 2011, "Finding a
'Kneedle' in a Haystack", section III). Used by every parameter choice (explore/r12_joint.py,
r12_params.py).

Kneedle, as in the article:
  1. smooth the curve (the article uses a smoothing spline and allows other smoothers; here the
     one-direction least-squares fit, pool adjacent violators, which has no tuning value);
  2. scale both axes to [0, 1];
  3. turn the curve so that it rises and bends downward (the article: "invert the graph" for
     elbows) and take the difference curve y - x;
  4. the candidate knees are the local maxima of the difference curve;
  5. each candidate gets the threshold T = y_lmx - S * (mean step between consecutive x);
  6. a candidate is a knee if the difference curve falls below T before the next local maximum.
     S = 1 (the value of the article's figure 2 and its best overall value, section IV.D).
Among the knees found, the one farthest from the chord (the largest difference) is used: the
article's approximation of the point of largest curvature.

Two checks the article does not cover come first, with stated values (no published value exists):
  flat      the curve changes by less than FLAT of its size: the parameter does nothing
  peak      the curve turns back: a point inside the range lies beyond both ends by more than
  valley    PEAK of the curve's spread (Kneedle assumes a curve that only rises or only falls).
            The knee is looked for on the part of the curve up to the turning point; if that part
            has under 4 points or no knee, the turning point itself is used (for a curve where
            lower is better, the lowest point is the best value)
Kinds returned: knee, knee before the peak/valley, flat, peak, valley, none (Kneedle finds no
knee: the curve has no bend, a stated value is kept).
"""
import numpy as np

FLAT, PEAK = 0.10, 0.20
S = 1.0


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


def difference(x, y):
    """Kneedle steps 2-3: the difference curve of a smoothed curve, turned so that it rises and
    bends downward (a knee is a local maximum of it)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xn = (x - x.min()) / (x.max() - x.min())
    yn = (y - y.min()) / (y.max() - y.min())
    if yn[-1] < yn[0]:                                 # falling curve: mirror y
        yn = 1 - yn
    # rising: a knee (bends down) has the curve above the diagonal; an elbow (bends up) below it,
    # and is turned into a knee by mirroring both axes, as the article does
    if np.mean(yn - xn) < 0:
        xn, yn = 1 - xn[::-1], 1 - yn[::-1]
        return xn, yn - xn, True
    return xn, yn - xn, False


def kneedle(x, y, s=S):
    """Index of the Kneedle knee of the smoothed curve (x, y), or None if there is none."""
    xn, d, flipped = difference(x, y)
    n = len(d)
    step = np.mean(np.diff(xn))
    lmx = [i for i in range(1, n - 1) if d[i - 1] < d[i] and d[i + 1] <= d[i]]
    knees = []
    for k, i in enumerate(lmx):
        t = d[i] - s * step
        stop = lmx[k + 1] if k + 1 < len(lmx) else n
        if np.any(d[i + 1:stop] < t):
            knees.append(i)
    if not knees:
        return None
    i = max(knees, key=lambda j: d[j])
    return n - 1 - i if flipped else i


def find(x, y):
    """(index, kind) of the curve's knee; kind: knee, knee before the peak/valley, flat, peak,
    valley or none (see above)."""
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
    i = kneedle(x, fit)
    if i is None:
        xn, d, _ = difference(x, fit)
        return int(np.argmax(np.abs(d))), "none"
    return int(i), "knee"
