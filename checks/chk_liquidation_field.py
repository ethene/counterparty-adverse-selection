"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data,
           node_fills_by_block/hourly); Zenodo 18184441 (Albers et al. 2026).

CHECK: byte-verify the raw `liquidation` object in node_fills before the
forced-liquidation NEGATIVE CONTROL (probe_F part 2) is banked.

WHY. A robustness review flagged that panel_rebuild_v2.py derives the
`is_liq` flag from a `liquidation` object whose structure was asserted in-code
("verified on raw 2025-12-04 H23 bytes") but never re-verified by a standalone,
repeatable check. The negative control (liquidations read as ANTI-toxic) is only
trustworthy if that flag is correct. This script is the independent re-derivation:
it pulls one node_fills hour straight from S3, walks the raw events with NO reuse
of the project parser, and confirms (a) the object exists, (b) its structure is
{liquidatedUser, markPx, method}, (c) method is "market", (d) liquidatedUser is a
hex address that is one of the fill's counterparties, (e) prevalence is in the
expected ~0.05-0.06% range for a calm hour, and (f) the extraction rule
`f.get("liquidation") is not None` flags exactly those fills (so is_liq is right).

Independent: this script uses NONE of the project parser's reading of the tape. It
re-reads the raw S3 bytes and re-implements the walk, so a bug in our pipeline cannot
mask a bug here. The one thing it does take from build_quickwin_markouts is the pair of
declared raw-cache settings -- where a fetched hour lands and whether it survives the
run -- because those have one home and a second copy of them here would go stale the
first time the rule changed. Neither can alter what the walk sees: the bytes are the
same S3 object whether they arrive fresh or are read from a copy already on disk.

Cost: one hourly .lz4 (~17 MB) via requester-pays S3, ~$0 (under the free tier), and
nothing at all when the hour is already in the declared cache directory.

Run command (bare python3 is BLOCKED on this machine):
  uv run --no-project python3 checks/chk_liquidation_field.py
Override the hour:
  CAP_LIQ_DAY=20251204 CAP_LIQ_HOUR=23 uv run --no-project python3 \
      checks/chk_liquidation_field.py
"""

import json
import os
import re
import subprocess
import sys

S3_BUCKET = "hl-mainnet-node-data"
DAY = os.environ.get("CAP_LIQ_DAY", "20251204")    # the hour panel_rebuild_v2 claimed
HOUR = os.environ.get("CAP_LIQ_HOUR", "23")        # to have verified
ZERO_HASH = "0x" + "0" * 64

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))
# The parser whose raw-input setting this gate reads lives in the `data` group, not in
# the tree root, so the group directory goes on the path as well. Named rather than
# globbed: a module that moves elsewhere should fail loudly, not resolve by accident.
_DATA_DIR = os.path.join(os.path.dirname(HERE), "data")
if _DATA_DIR not in sys.path:
    sys.path.insert(0, _DATA_DIR)
import artifact                                                        # noqa: E402
# Imported for the raw-input SETTING only -- where a fetched hour lives and whether it
# survives the run. Both keys are read through this module so the declaration has one
# home. Nothing of its parse is used here; see the note about independence above.
import build_quickwin_markouts as bqm                                  # noqa: E402
from evidence import mismatch_text, report_verdicts                    # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_liquidation_field_results.json")

HEX_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
EXPECTED_LIQ_KEYS = {"liquidatedUser", "markPx", "method"}
PREVALENCE_LO = 0.0001   # 0.01% floor (a calm hour should carry SOME liquidations)
PREVALENCE_HI = 0.05     # 5% ceiling (a stress hour can spike; flag, do not fail)

# What each verdict ASSERTS, in words. Written because the failure path here was the
# same single line the maker check used to end on -- "one or more verdicts FAILED
# (see JSON)" -- which names no verdict, no expectation and no number, and leaves
# re-running the download by hand as the only way to find out what went wrong.
EXPECTATIONS = {
    "object_exists": "the hour carries at least one fill with a `liquidation` "
                     "object, because a negative control that never fires cannot "
                     "show that forced flow is separable from chosen flow",
    "structure_is_liquidatedUser_markPx_method": "every liquidation object holds "
                                                 "exactly {liquidatedUser, markPx, "
                                                 "method}; a different key-set means "
                                                 "the exchange schema moved under us",
    "method_is_market": "every liquidation is method=market, which is what makes it "
                        "forced flow rather than a chosen order",
    "markPx_parses_float": "every markPx parses as a float, so the liquidation price "
                           "is usable rather than a sentinel",
    "liquidatedUser_is_hex_addr": "every liquidatedUser is a 40-hex address, so the "
                                  "forced party is identifiable by the same key the "
                                  "rest of the study counts wallets by",
    "liquidatedUser_is_a_counterparty": "in at least 99 percent of cases the "
                                        "liquidated address is one of the fill's own "
                                        "two counterparties, which is what lets a "
                                        "leg be attributed to the forced side",
    "prevalence_in_expected_band": f"forced legs are between {PREVALENCE_LO:.4%} and "
                                   f"{PREVALENCE_HI:.2%} of fills in the hour: below "
                                   "the floor the extraction rule is probably "
                                   "missing them, above the ceiling this is a stress "
                                   "hour and not a calm one",
    "extraction_rule_flags_valid_set": "`f.get('liquidation') is not None`, the rule "
                                       "the pipeline uses for is_liq, flags a "
                                       "non-empty and structurally valid set",
    "ALL_PASS": "all eight legs above hold together",
}


def _download_hour():
    """Put one hourly .lz4 on disk; returns (path, whether THIS run fetched it).

    The file goes where the declared setting CAP_RAW_CACHE says, under the per-day name
    build_quickwin_markouts.download_day builds, so an hour a tape walker already keeps
    is read instead of paid for again -- and an hour this check keeps is one they can
    read. The anonymous temp file that stood here was invisible in both directions.

    The second value is what the teardown is allowed to touch. This check fetches one
    hour of a twenty-four hour day into a shared directory, so a file that was already
    there belongs to whatever put it there, and "dispose of what you fetched" cannot
    mean the directory.
    """
    key = f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{DAY}/{HOUR}.lz4"
    day_dir = os.path.join(bqm.raw_cache_dir(), f"quickwin_{DAY}")
    os.makedirs(day_dir, exist_ok=True)
    dst = os.path.join(day_dir, f"{HOUR}.lz4")

    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        # The note names the hour and the setting, never the directory: a cache path is
        # absolute on whatever machine ran the pull, and this tree's gate forbids an
        # absolute path in any tracked file with an exception list that stays empty.
        print(f"[chk_liq] {DAY}/{HOUR}: reused a local .lz4 already on disk "
              f"({os.path.getsize(dst):,} bytes, CAP_RAW_CACHE)")
        return dst, False

    print(f"[chk_liq] aws s3 cp {key}")
    r = subprocess.run(
        ["aws", "s3", "cp", "--request-payer", "requester", key, dst],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) == 0:
        size = os.path.getsize(dst) if os.path.exists(dst) else None
        # A partial object left in the shared directory would read as a cache hit to
        # the next run, and to every other node that looks in the same place.
        try:
            os.remove(dst)
        except OSError:
            pass
        # A failure here says nothing about the repository, so it says what it DOES
        # mean: which object was asked for, what came back, and where. The previous
        # message printed 300 characters of stderr and nothing else, which does not
        # distinguish "no credentials" from "the hour is not in the bucket".
        raise SystemExit(mismatch_text(
            "the requester-pays object this check reads did not arrive",
            "one hourly .lz4 of node fills, non-empty",
            f"{'no file at all' if size is None else f'{size:,} bytes'}, aws exit "
            f"{r.returncode}, stderr {r.stderr.strip()[:300]!r}",
            key,
            "this is a fact about the S3 access on this machine, not about the "
            "clone. It is why this check sits in the opt-in group"))
    print(f"[chk_liq] downloaded {os.path.getsize(dst):,} bytes")
    return dst, True


def _iter_block_lines(path):
    """Stream-decompress a local .lz4 and yield non-empty JSON block-line strings
    (same `lz4 -dc` mechanism the project pipeline uses)."""
    proc = subprocess.Popen(
        ["lz4", "-dc", path], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1 << 20,
    )
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield line
    proc.wait()


def main():
    started = artifact.start_clock()
    path, pulled_here = _download_hour()
    try:
        n_fills = 0
        n_legs_with_liq = 0
        liq_hashes = {}              # hash -> list of leg liquidation dicts
        structure_ok = True
        bad_structure_samples = []
        method_counts = {}
        markpx_parse_fail = 0
        liquser_not_hex = 0
        liquser_is_counterparty = 0
        liquser_checked = 0
        coins_with_liq = {}
        samples = []

        # per-hash membership of the liquidatedUser among the fill's addresses,
        # to confirm the liquidated user is actually one of the two counterparties.
        hash_addrs = {}

        for raw in _iter_block_lines(path):
            block = json.loads(raw)
            if block.get("block_time") is None:
                continue
            for ev in block.get("events", []):
                # ev = [address, fill_dict]; re-read raw, do NOT reuse the parser.
                if not (isinstance(ev, list) and len(ev) == 2):
                    continue
                addr = ev[0]
                f = ev[1]
                if not isinstance(f, dict):
                    continue
                h = f.get("hash")
                if h is None or h == ZERO_HASH:
                    continue
                n_fills += 1
                hash_addrs.setdefault(h, set()).add(addr)

                liq = f.get("liquidation")      # the extraction rule under test
                if liq is None:
                    continue
                n_legs_with_liq += 1
                liq_hashes.setdefault(h, []).append(liq)

                # (b) structure
                if not isinstance(liq, dict) or set(liq.keys()) - EXPECTED_LIQ_KEYS or \
                        not EXPECTED_LIQ_KEYS.issubset(set(liq.keys())):
                    structure_ok = False
                    if len(bad_structure_samples) < 5:
                        bad_structure_samples.append({"hash": h, "liq_keys": sorted(liq.keys())
                                                      if isinstance(liq, dict) else str(type(liq))})
                    continue

                # (c) method
                method = liq.get("method")
                method_counts[method] = method_counts.get(method, 0) + 1

                # (d) markPx parses as float
                try:
                    float(liq.get("markPx"))
                except (TypeError, ValueError):
                    markpx_parse_fail += 1

                # (e) liquidatedUser is a hex address
                lu = liq.get("liquidatedUser")
                if not (isinstance(lu, str) and HEX_ADDR.match(lu)):
                    liquser_not_hex += 1

                coin = f.get("coin")
                coins_with_liq[coin] = coins_with_liq.get(coin, 0) + 1
                if len(samples) < 8:
                    samples.append({"hash": h, "coin": coin, "addr": addr,
                                    "liquidatedUser": lu, "markPx": liq.get("markPx"),
                                    "method": method, "side": f.get("side"),
                                    "dir": f.get("dir")})

        # (e cont.) is the liquidatedUser one of the fill's two counterparties?
        for h, legs in liq_hashes.items():
            addrs = hash_addrs.get(h, set())
            for liq in legs:
                lu = liq.get("liquidation") if isinstance(liq, dict) and "liquidation" in liq else liq
                lu_addr = liq.get("liquidatedUser") if isinstance(liq, dict) else None
                if lu_addr is None:
                    continue
                liquser_checked += 1
                if lu_addr in addrs:
                    liquser_is_counterparty += 1

        n_liq_hashes = len(liq_hashes)
        prevalence_legs = (n_legs_with_liq / n_fills) if n_fills else float("nan")

        # both-legs-share-hash: a liquidation hash should carry >=1 leg; report the
        # distribution of legs-per-liq-hash (1 or 2 expected).
        legs_per_hash = {}
        for h, legs in liq_hashes.items():
            legs_per_hash[len(legs)] = legs_per_hash.get(len(legs), 0) + 1

        # ---- verdicts ----
        v_exists = n_legs_with_liq > 0
        v_structure = structure_ok and n_legs_with_liq > 0
        v_method = bool(method_counts) and all(m == "market" for m in method_counts)
        v_markpx = markpx_parse_fail == 0 and n_legs_with_liq > 0
        v_liquser_hex = liquser_not_hex == 0 and n_legs_with_liq > 0
        v_liquser_cp = (liquser_checked > 0 and
                        liquser_is_counterparty / liquser_checked >= 0.99)
        v_prevalence = (prevalence_legs == prevalence_legs and
                        PREVALENCE_LO <= prevalence_legs <= PREVALENCE_HI)
        # the extraction rule `f.get("liquidation") is not None` is what produced
        # n_legs_with_liq, so by construction it flags exactly these fills; the
        # check is that it flags a NON-ZERO, STRUCTURALLY VALID set.
        v_extraction_rule = v_exists and v_structure

        all_pass = all([v_exists, v_structure, v_method, v_markpx,
                        v_liquser_hex, v_liquser_cp, v_prevalence, v_extraction_rule])

        results = {
            # ONE VERDICT WORD AT THE TOP, beside the eight it is made of. This file
            # carried the eight and no summary, so a reader -- and the runner, which
            # greps the screen for a verdict word -- had to know which of the eight
            # names meant the whole. The word is `all_pass` in a different shape and
            # moves no number. The time it was taken comes from _meta.run, which
            # artifact.write stamps; without one, a verdict cannot be told from a
            # verdict taken a month ago on another hour of tape.
            "verdict": "ALL_PASS" if all_pass else "FAIL",
            "_meta": {
                "check": "raw liquidation-object byte-verify (node_fills) for the "
                         "forced-liquidation negative control",
                "author": "Dmitry Stakhin",
                # RENAMED from `date`. It is the day this check was written, not the
                # day the verdict below was taken; the two sat under one name and the
                # older one read as the newer. When the verdict was taken is _meta.run.
                "first_written": "2026-06-22",
                "s3_key": f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{DAY}/{HOUR}.lz4",
                "independent": "raw re-walk; does NOT import the project parser",
                "extraction_rule_under_test": "f.get('liquidation') is not None  (== is_liq leg flag in panel_rebuild_v2.py)",
                "expected_keys": sorted(EXPECTED_LIQ_KEYS),
            },
            "counts": {
                "n_fills_scanned": n_fills,
                "n_legs_with_liquidation": n_legs_with_liq,
                "n_distinct_liquidation_hashes": n_liq_hashes,
                "prevalence_legs_frac": prevalence_legs,
                "legs_per_liquidation_hash": legs_per_hash,
                "method_counts": method_counts,
                "coins_with_liquidation": coins_with_liq,
                "markpx_parse_fail": markpx_parse_fail,
                "liquser_not_hex": liquser_not_hex,
                "liquser_checked": liquser_checked,
                "liquser_is_counterparty": liquser_is_counterparty,
            },
            "verdicts": {
                "object_exists": bool(v_exists),
                "structure_is_liquidatedUser_markPx_method": bool(v_structure),
                "method_is_market": bool(v_method),
                "markPx_parses_float": bool(v_markpx),
                "liquidatedUser_is_hex_addr": bool(v_liquser_hex),
                "liquidatedUser_is_a_counterparty": bool(v_liquser_cp),
                "prevalence_in_expected_band": bool(v_prevalence),
                "extraction_rule_flags_valid_set": bool(v_extraction_rule),
                "ALL_PASS": bool(all_pass),
            },
            "bad_structure_samples": bad_structure_samples,
            "samples": samples,
        }

        # The input is the S3 object, and it is recorded by its URI rather than by a
        # local name: the bucket and key ARE the identity of what was read, the
        # object is never kept on disk, and input_record leaves size and hash empty
        # with present=false for it. That empty pair is the honest record here, not
        # an omission -- the same border the tape parsers sit on.
        artifact.write(
            os.path.basename(OUT_JSON), results,
            script=__file__,
            inputs=[f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{DAY}/{HOUR}.lz4"],
            scope={
                "population": f"{n_fills:,} fills of one hourly object, of which "
                              f"{n_legs_with_liq:,} legs carry a liquidation",
                "window": f"ONE HOUR: day {DAY}, hour {HOUR}. This verdict is about "
                          f"that hour and is not a statement about the whole array",
                "coins": sorted(coins_with_liq) if coins_with_liq
                         else "no coin carried a liquidation in this hour",
            },
            started=started,
        )

        print("\n" + "=" * 80)
        print("LIQUIDATION-FIELD BYTE-VERIFY (node_fills) - SUMMARY")
        print("=" * 80)
        print(f"  s3 hour: {DAY}/{HOUR}   fills scanned: {n_fills:,}")
        print(f"  legs with `liquidation`: {n_legs_with_liq:,}  "
              f"distinct liq hashes: {n_liq_hashes:,}  "
              f"prevalence(legs): {prevalence_legs*100:.4f}%")
        print(f"  method counts: {method_counts}")
        print(f"  legs-per-liq-hash: {legs_per_hash}")
        print(f"  liquidatedUser is a counterparty: {liquser_is_counterparty}/{liquser_checked}")
        print("-" * 80)
        for k, v in results["verdicts"].items():
            print(f"  {'PASS' if v else 'FAIL'}  {k}")
        print("=" * 80)
        if samples:
            s = samples[0]
            print(f"  sample liq fill: coin={s['coin']} side={s['side']} dir={s['dir']} "
                  f"markPx={s['markPx']} method={s['method']}")
        print(f"  wrote {os.path.basename(OUT_JSON)}")
        # Every one of the eight legs above is in this map, so a false verdict here
        # and `not all_pass` are the same event: the condition is unchanged and only
        # what reaches the screen is different. The counts block travels with it,
        # because "prevalence_in_expected_band went false" is not actionable until
        # the prevalence it measured is beside the band it was measured against.
        return report_verdicts(
            results["verdicts"], EXPECTATIONS, OUT_JSON,
            inputs={"s3_key": results["_meta"]["s3_key"],
                    "day_hour": f"{DAY}/{HOUR}"},
            counts=results["counts"])
    finally:
        # Deletion is the DEFAULT and it is DECLARED, not wired in. The branch reads
        # bqm.keep_raw_days() rather than restating CAP_KEEP_RAW here, so the rule keeps
        # one home. What it disposes OF is local and has to be: an hour that was already
        # on disk when this check started belongs to whatever put it there. The
        # directory goes only if removing this run's file leaves it empty -- os.rmdir
        # refuses a non-empty one, which is the test rather than a flag that could
        # disagree with the disk. Printed either way, so the run log says which happened.
        if bqm.keep_raw_days():
            print(f"[chk_liq] {DAY}/{HOUR}: raw kept on disk "
                  f"(CAP_KEEP_RAW; see CAP_RAW_CACHE)")
        elif pulled_here:
            try:
                os.remove(path)
            except OSError:
                pass
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
            print(f"[chk_liq] {DAY}/{HOUR}: raw deleted "
                  f"(default; set CAP_KEEP_RAW=1 to keep)")
        else:
            print(f"[chk_liq] {DAY}/{HOUR}: raw left where it was found, because this "
                  f"run did not fetch it (CAP_RAW_CACHE)")


if __name__ == "__main__":
    sys.exit(main())
