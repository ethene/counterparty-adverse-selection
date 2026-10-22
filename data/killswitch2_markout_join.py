"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-15
References: Albers, Cucuringu, Howison, Shestopaloff, "An Open Book", Zenodo 10.5281/zenodo.18184441 (2026).
"""

# ---------------------------------------------------------------------------
# KILL-SWITCH 2 — reference-mid markout (early exploratory feasibility check).
#
# STATUS: superseded. This script was the first attempt to build a reference
# mid for the adverse-selection (markout) measurement by replaying the
# book_diffs event stream. The dataset has no native mid-price field, so a mid
# has to be reconstructed. Replaying new/remove/update events in file order
# reconstructs the visible book STATE correctly (best-bid / best-ask / mid), but
# the released SCHEMA.md book_diff example carries no documented per-event
# timestamp, so book events and trades cannot be placed on a common wall clock
# from this stream alone. Rather than infer an undocumented clock, the mid
# markout was re-derived in the main pipeline against a timestamped reference:
#   - i4_midmarkout.py computes the same maker adverse-selection markout on the
#     L2-book mid series (mid_series_BTC.npz / mid_series_ETH.npz, one timestamped
#     snapshot per grid step), joined entry = last snapshot at-or-before the fill
#     and horizon = first snapshot at-or-after fill + h seconds.
#   - that no-lookahead as-of join is independently ground-truthed by
#     checks/chk_join_nolookahead.py, and the book orientation and side/sign
#     conventions by checks/chk_book_orientation.py, chk_side_signconv.py and
#     chk_dir_vs_startpos.py (all "confirmed").
#
# What stays useful here is the sign convention: signed_markout below is the
# exact aggressor-profit convention carried into that validated pipeline, and
# BookReconstructor / the as-of helpers document how the book_diffs stream maps
# to a best-bid / best-ask / mid. Keep this file as a readable reference; run the
# validated measurement from i4_midmarkout.py.
#
# On-disk format (same as kill-switch 1):
#   - trades_2025_12.tar -> <YYYYMMDD>/<H>.gz, gzip JSON lines. Each trade has a
#     nanosecond ISO-8601 "time" field, "px", "sz", "side" ("A"=sell aggressor,
#     "B"=buy aggressor), "coin", and side_info[2].
#   - book_diffs_202512.tar -> <YYYYMMDD>/ex<H>.gz, gzip JSON lines. Each record:
#       {"user","oid","coin","side","px","raw_book_diff"}
#     where raw_book_diff is one of:
#       {"new":   {"sz":"..."}}                    -> order placed on the book
#       "remove"                                   -> order removed (cancel / full fill)
#       {"update":{"origSz":"...","newSz":"..."}}  -> partial fill, size reduced
#     side "A" = ask/sell resting order, "B" = bid/buy resting order. The oid
#     uniquely identifies a resting order; replaying new/remove/update in sequence
#     reconstructs the visible book, hence best-bid / best-ask / mid.
# ---------------------------------------------------------------------------

import gzip
import json
import os
import sys
from collections import defaultdict

import numpy as np

# Horizons (seconds) at which to mark out. Configurable.
MARKOUT_HORIZONS_S = (1.0, 10.0, 60.0)

COIN = "BTC"   # one coin per run; book reconstruction is per-coin
NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Shared streaming readers (same on-disk format as kill-switch 1)
# ---------------------------------------------------------------------------
def _iter_gz_lines(raw_bytes):
    text = gzip.decompress(raw_bytes).decode("utf-8")
    for line in text.split("\n"):
        line = line.strip()
        if line:
            yield line


def iter_jsonl_gz_dir(day_dir, prefix=""):
    """Yield JSON records from <day_dir>/<prefix><H>.gz for H in 0..23, in order.

    Trades use prefix="" (files "<H>.gz"); book diffs use prefix="ex"
    (files "ex<H>.gz"). Hours are NOT zero-padded.
    """
    for h in range(24):
        fp = os.path.join(day_dir, f"{prefix}{h}.gz")
        if not os.path.exists(fp):
            continue
        with open(fp, "rb") as fh:
            raw = fh.read()
        for line in _iter_gz_lines(raw):
            yield json.loads(line)


# ---------------------------------------------------------------------------
# Trade-time clock helper
# ---------------------------------------------------------------------------
def trade_time_ns(iso_ts):
    """ISO-8601 nanosecond string -> int nanoseconds since epoch.

    numpy datetime64[ns] parses the dataset's "2025-07-01T12:34:56.789012345"
    format including the 9-digit fractional part, which Python's datetime cannot.
    """
    return np.datetime64(iso_ts, "ns").astype("int64").item()


# ---------------------------------------------------------------------------
# Reference mid from the book_diffs stream
# ---------------------------------------------------------------------------
class BookReconstructor:
    """Replay new/remove/update events to track best-bid, best-ask, mid.

    Maintains, per coin, two price->resting-size maps (bids on side "B",
    asks on side "A") keyed by oid so updates/removes hit the right order.
    After each applied event we can read best_bid / best_ask / mid.
    """

    def __init__(self, coin):
        self.coin = coin
        # oid -> (side, px, sz) for every live order
        self.orders = {}
        # price ladders: px(float) -> aggregate resting size
        self.bids = defaultdict(float)  # side "B"
        self.asks = defaultdict(float)  # side "A"

    def apply(self, rec):
        if rec.get("coin") != self.coin:
            return
        rbd = rec.get("raw_book_diff")
        oid = rec.get("oid")
        side = rec.get("side")
        try:
            px = float(rec["px"])
        except (KeyError, TypeError, ValueError):
            return
        ladder = self.bids if side == "B" else self.asks

        if rbd == "remove":
            prev = self.orders.pop(oid, None)
            if prev is not None:
                _, ppx, psz = prev
                book = self.bids if prev[0] == "B" else self.asks
                book[ppx] -= psz
                if book[ppx] <= 1e-12:
                    book.pop(ppx, None)
            return

        if isinstance(rbd, dict) and "new" in rbd:
            sz = float(rbd["new"]["sz"])
            self.orders[oid] = (side, px, sz)
            ladder[px] += sz
            return

        if isinstance(rbd, dict) and "update" in rbd:
            new_sz = float(rbd["update"]["newSz"])
            prev = self.orders.get(oid)
            if prev is not None:
                _, ppx, psz = prev
                book = self.bids if prev[0] == "B" else self.asks
                book[ppx] += (new_sz - psz)
                if book[ppx] <= 1e-12:
                    book.pop(ppx, None)
                self.orders[oid] = (prev[0], ppx, new_sz)
            else:
                # update for an order we never saw a "new" for: treat as a place
                self.orders[oid] = (side, px, new_sz)
                ladder[px] += new_sz
            return

    def best_bid(self):
        return max(self.bids) if self.bids else None

    def best_ask(self):
        return min(self.asks) if self.asks else None

    def mid(self):
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return 0.5 * (bb + ba)


def build_mid_series(book_day_dir, coin):
    """Replay one day of book diffs and emit a time-ordered mid series.

    Returns (ts_ns_array, mid_array), both sorted by time, suitable for an
    as-of join. One mid sample is recorded after every event that changes the
    top of book.

    This is the exploratory book_diffs-replay path (see the module header). It
    depends on a per-event book clock via event_time_ns; the released book_diff
    schema does not document one, which is why the validated mid markout is built
    from timestamped L2 snapshots in i4_midmarkout.py instead.
    """
    book = BookReconstructor(coin)
    ts_list = []
    mid_list = []
    last_mid = None
    for rec in iter_jsonl_gz_dir(book_day_dir, prefix="ex"):
        book.apply(rec)
        m = book.mid()
        if m is None:
            continue
        t = event_time_ns(rec)  # per-event book clock; see the module header
        if m != last_mid:
            ts_list.append(t)
            mid_list.append(m)
            last_mid = m
    if not ts_list:
        raise ValueError(f"no mid samples built for {coin} in {book_day_dir}")
    ts = np.asarray(ts_list, dtype=np.int64)
    mid = np.asarray(mid_list, dtype=np.float64)
    order = np.argsort(ts, kind="stable")
    return ts[order], mid[order]


def event_time_ns(rec):
    """Nanosecond timestamp for a book_diff record, when the record carries one.

    The released book_diff schema does not document a per-event timestamp, so
    this returns a time only when a record actually exposes a "time" or "ts"
    field. When neither is present it raises rather than inventing a wall clock;
    the validated pipeline avoids the issue entirely by joining against the
    timestamped L2 snapshots in i4_midmarkout.py.
    """
    if "time" in rec:
        return trade_time_ns(rec["time"])
    if "ts" in rec:  # nanoseconds-since-epoch integer, per order-status convention
        return int(rec["ts"])
    raise NotImplementedError(
        "book_diff records in this dataset carry no documented per-event "
        "timestamp; use the timestamped L2-snapshot mid in i4_midmarkout.py for "
        "the validated markout."
    )


# ---------------------------------------------------------------------------
# As-of join + markout
# ---------------------------------------------------------------------------
def asof_mid(ts_sorted, mid_sorted, query_ns):
    """Mid prevailing at-or-before query_ns (last-known-value as-of join).

    Returns np.nan if query_ns precedes the first book sample.
    """
    idx = np.searchsorted(ts_sorted, query_ns, side="right") - 1
    if idx < 0:
        return np.nan
    return float(mid_sorted[idx])


def signed_markout(trade_side, mid_at_trade, mid_at_horizon):
    """Markout in price units, signed so that POSITIVE = the AGGRESSOR profited.

    side "B" = buy aggressor: aggressor is long, gains if mid rises later
        markout = (mid_h - mid_0)
    side "A" = sell aggressor: aggressor is short, gains if mid falls later
        markout = (mid_0 - mid_h)
    A positive markout means the aggressor (taker) picked off the resting maker,
    i.e. the maker faced adverse selection. Flip the sign for the maker's view.
    """
    if np.isnan(mid_at_trade) or np.isnan(mid_at_horizon):
        return np.nan
    if trade_side == "B":
        return mid_at_horizon - mid_at_trade
    elif trade_side == "A":
        return mid_at_trade - mid_at_horizon
    return np.nan


def run(trades_day_dir, book_day_dir, coin=COIN):
    print(f"[ks2] coin={coin}")
    print(f"[ks2] building reference mid from book diffs: {book_day_dir}")
    ts_mid, mid = build_mid_series(book_day_dir, coin)  # exploratory book_diffs-replay path
    print(f"[ks2] mid samples: {ts_mid.size:,}")

    horizons_ns = [int(h * NS_PER_S) for h in MARKOUT_HORIZONS_S]
    sums = {h: 0.0 for h in MARKOUT_HORIZONS_S}
    n = {h: 0 for h in MARKOUT_HORIZONS_S}

    print(f"[ks2] joining trades: {trades_day_dir}")
    for tr in iter_jsonl_gz_dir(trades_day_dir, prefix=""):
        if str(tr.get("coin", "")).upper() != coin.upper():
            continue
        t0 = trade_time_ns(tr["time"])
        side = tr.get("side")
        m0 = asof_mid(ts_mid, mid, t0)
        for hs, hns in zip(MARKOUT_HORIZONS_S, horizons_ns):
            mh = asof_mid(ts_mid, mid, t0 + hns)
            mo = signed_markout(side, m0, mh)
            if not np.isnan(mo):
                sums[hs] += mo
                n[hs] += 1

    print("\n" + "=" * 60)
    print("KILL-SWITCH 2 — MEAN AGGRESSOR MARKOUT BY HORIZON")
    print("=" * 60)
    for hs in MARKOUT_HORIZONS_S:
        mean = sums[hs] / n[hs] if n[hs] else float("nan")
        print(f"  h={hs:>5.0f}s : mean markout = {mean:+.6f}  (n={n[hs]:,})")
    print("=" * 60)
    print("Positive => taker profits at horizon => makers adversely selected.")


def main():
    if len(sys.argv) not in (3, 4):
        print("usage: python killswitch2_markout_join.py "
              "<trades_day_dir> <book_diffs_day_dir> [COIN]")
        print("  e.g. .../trades/20251215  .../book_diffs/20251215  BTC")
        sys.exit(2)
    trades_day_dir = sys.argv[1]
    book_day_dir = sys.argv[2]
    coin = sys.argv[3] if len(sys.argv) == 4 else COIN
    print("[ks2] NOTE: exploratory kill-switch. The validated mid markout is "
          "i4_midmarkout.py (timestamped L2 snapshots). This book_diffs-replay "
          "path runs only if the book records expose a per-event timestamp.")
    run(trades_day_dir, book_day_dir, coin)


if __name__ == "__main__":
    main()
