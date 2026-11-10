"""
Stage 4: price jumps in the crypto up/down markets, with their own parameters (CX).

Runs stage 3 (s3_events.py: slots, window, jumps, next trades, and every slot with trades for
the calibration error b(p)) on the crypto trades (tmp/buckets_cx, from s1x_bucket.py) with the
crypto values of the slot length, cuts, settle band, price clip and next trades.

Writes tmp/events_cx/<slot>/e<k>.parquet (jumps) and r<k>.parquet (every slot).
Usage: python s4_paths.py cxmoves <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import sys

import s2_events as s2
import s3_events as s3

CX = dict(slot=60, min_pts=0.18, cut_start=0.0, cut_end=0.075, edge=0.03, clip=0.03, next_n=5, next_max=120)  # crypto (elbow)


def main(mode, buckets):
    assert mode == "cxmoves", "the only mode used by the report"
    s2.SRC = "tmp/buckets_cx"
    s3.OUT_ROOT = "tmp/events_cx"
    s2.BAR = CX["slot"]          # s3 then also writes every crypto slot, for b(p)
    s2.LIFE_CUT_START, s2.LIFE_CUT_END, s2.EDGE, s2.CLIP = CX["cut_start"], CX["cut_end"], CX["edge"], CX["clip"]
    s3.ENTRY_N, s3.ENTRY_MAX = CX["next_n"], CX["next_max"]
    s3.main(CX["slot"], buckets)


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]])
