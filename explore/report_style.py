"""
Shared plot style for the report: the official Rose Pine Dawn matplotlib theme
(explore/rose-pine-dawn.mplstyle, from github.com/h4pZ/rose-pine-matplotlib) plus fixed
semantic colours, so the same thing has the same colour in every figure.

  1 trader = love, a few traders = gold, a crowd = pine (groups from r02_persistence)
  up move = foam, down move = rose, neutral / reference = muted
"""
import os

import sys

import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
from r02_persistence import TG_LABELS  # noqa: E402

plt.style.use(os.path.join(os.path.dirname(__file__), "rose-pine-dawn.mplstyle"))
plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlecolor": "#575279", "legend.frameon": False, "savefig.dpi": 150,
    "grid.color": "#dfdad9", "grid.linewidth": 0.6, "axes.edgecolor": "#cecacd",
})

BASE, SURFACE, OVERLAY = "#faf4ed", "#fffaf3", "#f2e9e1"
MUTED, SUBTLE, TEXT = "#9893a5", "#797593", "#575279"
HL_LOW, HL_MED, HL_HIGH = "#f4ede8", "#dfdad9", "#cecacd"
LOVE, GOLD, ROSE, PINE, FOAM, IRIS = "#b4637a", "#ea9d34", "#d7827e", "#286983", "#56949f", "#907aa9"

TG = dict(zip(TG_LABELS, (LOVE, GOLD, PINE)))
TG_LABEL = {k: "1 trader" if k == "1" else f"{k} traders" for k in TG_LABELS}
UP, DOWN = FOAM, ROSE
