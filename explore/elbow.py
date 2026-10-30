"""
The elbow (knee) of a curve, by the Kneedle rule (Satopaa et al. 2011): with both axes scaled
to [0, 1], the knee is the point farthest from the straight line through the first and the
last point. Used by every parameter choice (explore/r12_joint.py, r12_params.py, r12_f9.py).
"""
import numpy as np


def knee(x, y):
    """Index of the knee of the curve (x, y), on a linear axis."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xn = (x - x.min()) / (x.max() - x.min())
    yn = (y - y.min()) / (y.max() - y.min())
    dx, dy = xn[-1] - xn[0], yn[-1] - yn[0]
    dist = np.abs(dy * (xn - xn[0]) - dx * (yn - yn[0])) / np.hypot(dx, dy)
    return int(np.argmax(dist))
