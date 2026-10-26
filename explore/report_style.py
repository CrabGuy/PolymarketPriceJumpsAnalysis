"""
Shared plot style for the report: the official Rose Pine Dawn matplotlib theme
(explore/rose-pine-dawn.mplstyle, from github.com/h4pZ/rose-pine-matplotlib) plus fixed
semantic colours, so the same thing has the same colour in every figure.

  1 trader = love, 2-3 traders = gold, 4+ traders = pine
  up move = foam, down move = rose, neutral / reference = muted
"""
import os

import matplotlib.pyplot as plt

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

TG = {"1": LOVE, "2-3": GOLD, "4+": PINE}
TG_LABEL = {"1": "1 trader", "2-3": "2-3 traders", "4+": "4+ traders"}
UP, DOWN = FOAM, ROSE
