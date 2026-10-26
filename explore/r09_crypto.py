"""
Round 9: do the new jump rules (10 points; first and last 10% of a market's life left out)
change the crypto up/down results (F8)?

Compares four versions on the 1-minute jumps: the old window (cut only at the settle moment,
local_data/r05/events_cx/60) or the new one (local_data/r09/events_cx/60, remote/s4_paths.py
cxmoves after round 9), each with the old rule (0.4 in log-odds) or the new one (10 points).
Per version: jumps, markets, raw overshoot (price vs outcome, no baseline, as in the F8
plots) at the close and at the next trades by trader group, and for crowd jumps (4+) by
whether the other coin's market moved the same way in that minute.

Output: local_data/r09_crypto.csv. Usage: python explore/r09_crypto.py
"""
import sys

import pandas as pd

sys.path.insert(0, "explore")
import r05_updown as ud  # noqa: E402

DIRS = {"old window": "local_data/r05/events_cx/60/e*.parquet", "new window": "local_data/r09/events_cx/60/e*.parquet"}
RULES = {"0.4 log-odds": dict(min_pts=0, min_logit=0.4), "10 points": dict(min_pts=0.10, min_logit=0)}


def main():
    info = ud.market_info()
    paths = ud.load_paths(info)
    rows = []
    for wname, path in DIRS.items():
        ud.EVENTS = path
        for rname, kw in RULES.items():
            b = ud.load_moves(info, **kw)
            b = ud.confirm(b, paths)
            b = b[b.entry_vwap.notna()].copy()
            b["raw_c"], b["raw_e"] = b.sgn * (b.p_close - b.outcome), b.sgn * (b.entry_vwap - b.outcome)
            r = {"window": wname, "rule": rname, "jumps": len(b), "markets": b.market.nunique()}
            for tg, x in b.groupby("tg", observed=True):
                r[f"close_{tg}"], r[f"next_{tg}"] = ud.share(x, "raw_c"), ud.share(x, "raw_e")
            for c, x in b[b.tg == "4+"].groupby("conf_other"):
                r[f"4+ other coin {c}"] = ud.share(x, "raw_c")
            rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv("local_data/r09_crypto.csv", index=False)
    pd.set_option("display.width", 250)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
