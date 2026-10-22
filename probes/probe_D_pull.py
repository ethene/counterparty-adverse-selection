"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: [Hyperliquid public info API (fundingHistory); Binance USDT-M futures
            fundingRate + spot klines]

PROBE-D DATA PULL. Fetches the three funding-clock inputs Probe D needs and writes
them as parquet under ../02_data/raw/funding/ in one venue-neutral funding
schema, so that a Hyperliquid row and a Binance row carry the same columns and one
loader reads both (venue, symbol, funding_time_ms, rate_native, interval_hours,
apy_native_pct, mark_price_usd, premium_index). Coins BTC/ETH/SOL.
Window = Aug 1 2025 -> May 31 2026 (covers the markout panel's 8 monthly windows).

  (1) HL hourly funding+premium     -> hl_funding.parquet
  (2) Binance USDT-M 8h funding+mark -> binance_funding.parquet
  (3) Binance spot 1h klines (close) -> binance_spot_klines.parquet  (for basis)

NEVER fetches the HL oracle/mark (circular reference). Whole pull is <5 min, <few MB.
No credentials. Uses only the public auth-free endpoints already live-verified back
to Aug 2025, fetched with the standard library alone and one request at a time, with a
0.3s pause between pages of the hourly Hyperliquid history.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import sys
import urllib.error
import urllib.parse
import urllib.request

# Resolved from this file's own location, not from the working directory, so the import
# works wherever the pull is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import settings as H  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "02_data", "raw", "funding")
HL_INFO = "https://api.hyperliquid.xyz/info"
BN_FAPI = "https://fapi.binance.com"
BN_SPOT = "https://api.binance.com"
UA = "counterparty-adverse-selection/probe-D-funding"

# What to pull is decided by what the panel carries, not by a list typed here: the
# funding series exists only to be joined onto the panel, so a coin the panel does not
# hold is a download nobody reads, and a coin the panel gains without this line gaining
# it is a silent hole in the join. It used to read COINS = ["BTC", "ETH", "SOL"], which
# is what the declaration returns for the panel, so binding it downloads the same three.
COINS = [H.coin_labels("panel")[c] for c in sorted(H.coin_labels("panel"))]

# Binance's ticker for each coin: a property of the other venue, not a setting of this
# study, so it stays here. A coin added to the panel without a ticker added here raises
# on the lookup rather than being skipped, which is the loud failure of the two.
BN_SYM = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
PAGE_SLEEP = 0.3
HOUR_MS = 3_600_000


def _to_ms(s: str) -> int:
    d = dt.datetime.fromisoformat(s + "T00:00:00").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def _post_json(url, payload, timeout=30, retries=8, backoff=2.0):
    body = json.dumps(payload).encode()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json", "User-Agent": UA},
                method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429,) or 500 <= e.code < 600:
                time.sleep(min(backoff * (2 ** i), 60.0)); continue
            raise
        except Exception as e:
            last = e
            time.sleep(min(backoff * (2 ** i), 60.0))
    raise last


def _get_json(url, params=None, timeout=30, retries=6, backoff=0.5):
    qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    full = url + ("?" + qs if qs else "")
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (418, 429) or 500 <= e.code < 600:
                time.sleep(backoff * (2 ** i)); continue
            raise
        except Exception as e:
            last = e
            time.sleep(backoff * (2 ** i))
    raise last


def hl_funding(coin, start_ms, end_ms):
    """Page HL fundingHistory ASC (<=500/page); rate_native + premium_index hourly."""
    out, cursor = [], int(start_ms)
    while cursor < end_ms:
        rows = _post_json(HL_INFO, {"type": "fundingHistory", "coin": coin, "startTime": cursor})
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        last_ts = max(int(r["time"]) for r in rows)
        if last_ts <= cursor or len(rows) < 500:
            break
        cursor = last_ts + 1
        time.sleep(PAGE_SLEEP)
    recs = []
    for r in out:
        if int(r["time"]) > end_ms:
            continue
        prem = r.get("premium")
        recs.append({"venue": "hyperliquid", "symbol": coin,
                     "funding_time_ms": int(r["time"]),
                     "rate_native": float(r["fundingRate"]),
                     "interval_hours": 1.0,
                     "apy_native_pct": float(r["fundingRate"]) * 24 * 365 * 100,
                     "mark_price_usd": None,
                     "premium_index": float(prem) if prem not in (None, "") else None})
    return recs


def bn_funding(sym, start_ms, end_ms):
    """Page Binance fundingRate (<=1000/page); 8h cadence, carries markPrice."""
    out, t = [], int(start_ms)
    while t < end_ms:
        rows = _get_json(BN_FAPI + "/fapi/v1/fundingRate",
                         {"symbol": sym, "startTime": t, "endTime": end_ms, "limit": 1000})
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        last_ts = max(int(r["fundingTime"]) for r in rows)
        if last_ts <= t or len(rows) < 1000:
            break
        t = last_ts + 1
        time.sleep(0.05)
    recs = []
    for r in out:
        mk = r.get("markPrice")
        try:
            mkv = float(mk) if mk not in (None, "", "0") else None
        except ValueError:
            mkv = None
        recs.append({"venue": "binance-usdtm", "symbol": sym,
                     "funding_time_ms": int(r["fundingTime"]),
                     "rate_native": float(r["fundingRate"]),
                     "interval_hours": 8.0,
                     "apy_native_pct": float(r["fundingRate"]) * 3 * 365 * 100,
                     "mark_price_usd": mkv,
                     "premium_index": None})
    return recs


def bn_spot_klines(sym, start_ms, end_ms):
    """Page Binance spot 1h klines; keep openTime + close for the basis denominator."""
    out, t = [], int(start_ms)
    while t < end_ms:
        rows = _get_json(BN_SPOT + "/api/v3/klines",
                         {"symbol": sym, "interval": "1h",
                          "startTime": t, "endTime": end_ms, "limit": 1000})
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        last_ts = max(int(k[0]) for k in rows)
        if last_ts <= t or len(rows) < 1000:
            break
        t = last_ts + HOUR_MS
        time.sleep(0.05)
    return [{"symbol": sym, "open_time_ms": int(k[0]), "close": float(k[4])} for k in out]


def _write_parquet(records, path, schema):
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = {name: [] for name, _ in schema}
    for r in records:
        for name, _ in schema:
            cols[name].append(r.get(name))
    arrays = [pa.array(cols[name], type=typ) for name, typ in schema]
    tbl = pa.table(arrays, names=[name for name, _ in schema])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pq.write_table(tbl, path)
    print(f"  wrote {len(records):,} rows -> {path}")


def main():
    import pyarrow as pa
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-08-01")
    ap.add_argument("--end", default="2026-05-31")
    args = ap.parse_args()
    s, e = _to_ms(args.start), _to_ms(args.end)
    fund_schema = [("venue", pa.string()), ("symbol", pa.string()),
                   ("funding_time_ms", pa.int64()), ("rate_native", pa.float64()),
                   ("interval_hours", pa.float64()), ("apy_native_pct", pa.float64()),
                   ("mark_price_usd", pa.float64()), ("premium_index", pa.float64())]
    spot_schema = [("symbol", pa.string()), ("open_time_ms", pa.int64()),
                   ("close", pa.float64())]

    print(f"Probe-D pull | {args.start} -> {args.end} | coins {COINS}")
    hl, bn, sp = [], [], []
    for c in COINS:
        print(f"HL funding {c} ..."); hl += hl_funding(c, s, e)
    for c in COINS:
        print(f"BN funding {BN_SYM[c]} ..."); bn += bn_funding(BN_SYM[c], s, e)
    for c in COINS:
        print(f"BN spot klines {BN_SYM[c]} ..."); sp += bn_spot_klines(BN_SYM[c], s, e)

    _write_parquet(hl, os.path.join(OUT_DIR, "hl_funding.parquet"), fund_schema)
    _write_parquet(bn, os.path.join(OUT_DIR, "binance_funding.parquet"), fund_schema)
    _write_parquet(sp, os.path.join(OUT_DIR, "binance_spot_klines.parquet"), spot_schema)
    print("Probe-D pull complete.")


if __name__ == "__main__":
    main()
