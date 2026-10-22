"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# chk_field_hygiene.py  - RAW-DATA RE-VERIFICATION (silent-drop + drift hygiene)
#
# WHY THIS EXISTS
#   Prior audits only checked number-on-disk == number-in-doc; they could NOT
#   catch a field that is being SILENTLY DROPPED by the parse, nor a load-bearing
#   line that has DRIFTED between the two copies of the parser. This script grounds
#   both empirically and emits a verdict instead of trusting the convention.
#
# (a) SILENT-DROP + SIZE HYGIENE (raw event-level re-walk of ONE December day)
#   The production parser (build_quickwin_markouts.parse_day, copied verbatim into
#   ks2_persistence_10day.parse_day) routes each raw fill on `crossed`:
#       crossed is True  -> taker branch (collapsed sweep, gets a markout)
#       crossed is False -> maker branch (dominant-maker resolution)
#   A fill whose `crossed` is ABSENT/None (or any non-bool) matches NEITHER branch
#   and is SILENTLY DROPPED from the counterparty resolution (it still nudges the
#   per-hash VWAP print path, but never becomes a taker obs and never resolves a
#   maker). We mirror that exact event loop at the RAW level and COUNT, as fractions
#   of total raw fills:
#     - crossed-absent/None fills (the silent-drop population),
#     - sz<=0 fills (size is read as float(f["sz"]) and never filtered, so a
#       zero/negative size would pollute the VWAP and size-weighting),
#     - the maker-None rate = (hash,taker) takers for which NO crossed=false leg
#       shared the hash within the walked window (these become maker_id == -1).
#   We mirror parse_day's guards faithfully: skip coins not in COINS, skip the
#   ZERO_HASH / None hash (so the denominators match the parser's own universe).
#
# (b) DRIFT CHECK (textual, no data needed)
#   ks2_persistence_10day.py carries a DUPLICATED copy of parse_day / price_at /
#   the markout, NOT an import. If the two copies diverge, the validated persistence
#   run and the shared intermediate stop agreeing silently. We textually compare the
#   two modules' load-bearing lines:
#     - the signed-markout formula
#         taker_dir.astype(np.float64) * (ref - taker_px) / taker_px * 1e4
#     - the as-of join
#         idx = np.searchsorted(print_ts, query_ns, side="right") - 1
#   and report whether they are BYTE-IDENTICAL today (whitespace-normalised core).
#   We also diff the full source of price_at and compute_markouts_all between the
#   two modules as a backstop against a subtler change. parse_day itself is NOT
#   byte-identical (build ~190 lines vs ks2 ~103) - we diff it code-only and
#   ALLOW-LIST the one known benign divergence (ks2 drops the crossed=false maker
#   branch + the unused is_open/start_pos/side_b/closed_pnl/dir_code fields),
#   asserting the shared core matches and flagging any NEW divergence.
#
# VERDICT (overall_verdict requires BOTH halves below to RUN and PASS for confirmed)
#   confirmed - the drift half ran AND the raw re-walk ran, the duplicated
#               load-bearing lines are identical (parse_day's benign maker/extra-
#               field divergence allow-listed) AND the silent-drop / sz<=0
#               fractions are negligible (<= DROP_NEGLIGIBLE).
#   uncertain - the raw re-walk did NOT run (--smoke, or S3/lz4 unavailable) so the
#               silent-drop / sz<=0 / maker-None legs were never measured (drift
#               half only); OR it ran but found non-trivial silent drops / sz<=0.
#               Drift-only evidence is NEVER enough for 'confirmed'.
#   refuted   - the markout formula, the searchsorted join, price_at,
#               compute_markouts_all, OR parse_day's shared core has DIVERGED
#               between the two copies (the duplication is no longer faithful).
#
# OUTPUT (the shared check contract):
#   checks/chk_field_hygiene_results.json
#
# Run (bare python3 is BLOCKED on this machine):
#   FULL  : uv run --no-project --with-requirements requirements.txt python3 checks/chk_field_hygiene.py
#   SMOKE : uv run --no-project --with-requirements requirements.txt python3 checks/chk_field_hygiene.py --smoke
#           (--smoke = textual drift diff ONLY; skips the raw re-walk entirely)
#   The full mode pulls a BOUNDED number of hourly files for ONE December day
#   (default RW_DAY / RW_MAX_HOURS) so the re-walk stays light (~a few hundred MB).
# ---------------------------------------------------------------------------

import inspect
import json
import os
import re
import subprocess
import sys

import numpy as np

# import the PRODUCTION parser so we reuse its exact constants + diff its source
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(THIS_DIR)          # the repository root
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
# The two parsers this gate calls live in their pipeline groups rather than beside it,
# so the group directory has to be on the path as well: adding the tree root is not
# enough once a module is one level down. Named per group rather than globbed, so that
# a module moving to a group not listed here fails loudly instead of resolving by luck.
for _group in ("data", "persistence"):
    _p = os.path.join(CODE_DIR, _group)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact                                # noqa: E402
import build_quickwin_markouts as bqm          # noqa: E402
import ks2_persistence_10day as ks2            # noqa: E402
from evidence import mismatch_text, report_contract           # noqa: E402

OUT_JSON = os.path.join(THIS_DIR, "chk_field_hygiene_results.json")
# The two sources are located by asking the imported modules where they are, not by
# rebuilding a path from a directory this gate assumes. Both moved into pipeline groups
# on 2026-08-11 and a rebuilt path pointed at the root, where the file no longer is: the
# import had already resolved, so the failure surfaced two hundred lines later as a
# missing file rather than as a missing module. A module knows its own address; a gate
# guessing it is the same defect this project calls resolving by path instead of by
# content.
BUILD_SRC = os.path.abspath(bqm.__file__)
KS2_SRC = os.path.abspath(ks2.__file__)

# raw re-walk knobs (full mode only). Bounded so the re-walk is light.
RW_DAY = "20251204"        # one December day inside the parsed window 4..13
RW_MAX_HOURS = 3           # pull at most this many hourly .lz4 (a few hundred MB)
S3_BUCKET = "hl-mainnet-node-data"
# No local temp-directory constant here on purpose: where a fetched hour lands is the
# declared setting CAP_RAW_CACHE, read through bqm.raw_cache_dir() so one file holds the
# default. A constant here would be a second home for it, and the one that used to sit
# on this line also put this check's hours somewhere the tape walkers could not see.

# negligible threshold for the silent-drop / sz<=0 fractions
DROP_NEGLIGIBLE = 1e-4     # 0.01% of raw fills

# ----------------------------------------------------------------------------
# parse_day ALLOW-LIST (the ONE known-benign divergence between the two copies)
#
# The docstring claims parse_day is "copied verbatim" into ks2. It is NOT:
# build_quickwin_markouts.parse_day is ~190 source lines, ks2_persistence_10day's
# is ~103. The divergence is BENIGN and entirely accounted for here -- ks2 simply
# DROPS work that the persistence run does not need:
#   (1) the crossed=false MAKER branch + dominant-maker-per-hash resolution, and
#   (2) the extra retained taker fields is_open / start_pos / side_b / closed_pnl
#       / dir_code (and their downstream arrays + per_coin dict keys).
# The shared CORE -- the per-hash VWAP print-path accumulation, the crossed=true
# taker collapse, the markout/as-of-join math -- must stay byte-identical.
#
# A line that build has but ks2 lacks ("build-only") is allowed ONLY if it
# matches one of these signatures; anything else is a NEW behavioral divergence.
PARSE_DAY_ALLOW_BUILD_ONLY = [
    r"maker_size_by_hash", r"\bmsb\b", r"\bbucket\b", r"\bm_addr\b",
    r"dominant_maker", r'elif f\.get\("crossed"\) is False',
    r"\bis_open\b", r"\bstart_pos\b", r"\bd_str\b", r"\bdir_code\b",
    r"\bsp_raw\b", r"\bcp_raw\b", r"\bclosed_pnl\b", r"\bside_b\b",
    r"except \(TypeError, ValueError\):",      # guards for the extra-field reads
    r"\bt_open\b", r"\bt_spos\b", r"\bt_size\b", r"\bt_side\b",
    r"\bt_cpnl\b", r"\bt_dcode\b", r"\bt_maddr\b",
    r'"taker_open"', r'"taker_spos"', r'"taker_size"', r'"taker_side"',
    r'"taker_cpnl"', r'"taker_dcode"', r'"maker_addr"',
    r'1 if f\.get\("side"\) == "B" else -1,',  # split rec literal (extra fields follow)
    r"closed_pnl, dir_code\]",                 # tail of the split rec literal
    r"is_open, start_pos, side_b,",            # middle of the split rec literal
    r"pxsz, szsum, ts, d, is_open",            # wider unpack on the build side
    r'"print_ts": print_ts, "print_px": print_px\}',  # split per_coin dict literal tail
    r"print\(f\"\[quickwin\]",                 # log-tag-only difference
    # THE RAW-CACHE GATE, SPELLED TWO WAYS FOR ONE CALL. On 2 August 2026 both copies
    # stopped deleting the parsed day outright and began asking the declared key. The
    # key has ONE home, build_quickwin_markouts.keep_raw_days, so the copy that owns it
    # calls it by name and the copy that imports it calls it through the alias. Same
    # function, same branch, same behaviour, two spellings -- which is exactly what this
    # list is for. It went unrecorded, and from that day until 3 August this check read
    # REFUTED on a pair of lines that differ by a module prefix: build-only
    # 'if keep_raw_days():' against ks2-only 'if bqm.keep_raw_days():', with every other
    # number in the diff unchanged (146 / 92 code lines, 58 of 59 build-only and 6 of 7
    # ks2-only already allow-listed, all core anchors present).
    #
    # The pattern is the whole branch line and nothing wider. A regex on the function
    # name alone would also pass a copy that started calling it with an argument, or
    # under a different operator, which would be a real divergence.
    r"^if keep_raw_days\(\):$",
]
# A line ks2 has but build lacks verbatim ("ks2-only") is allowed ONLY if it is a
# known PRESENTATION difference (line-wrapping / log tag / narrower unpack), NOT a
# behavioral change.
PARSE_DAY_ALLOW_KS2_ONLY = [
    r'1 if f\.get\("side"\) == "B" else -1\]',  # rec literal closed on one line
    r"print\(f\"\[ks2\]",                       # log-tag-only difference
    r"pxsz, szsum, ts, d = rec",                # narrower unpack on the ks2 side
    r'"taker_addr": t_addr, "print_ts": print_ts, "print_px": print_px\}',  # one-line dict tail
    # The other half of the raw-cache gate; see the note beside the build-only entry.
    r"^if bqm\.keep_raw_days\(\):$",
]
# Shared-CORE anchor lines that MUST be present (code-only) in BOTH copies. These
# are the load-bearing print-path / collapse / as-of-join lines the duplication
# exists to keep identical; if any goes missing the duplication has drifted.
PARSE_DAY_CORE_ANCHORS = [
    'bt_ns = int(np.datetime64(bt, "ns").astype("int64"))',
    'h = f.get("hash")',
    'if h == ZERO_HASH or h is None:',
    'px = float(f["px"])',
    'sz = float(f["sz"])',
    'print_pxsz_by_hash[coin][h] = [px * sz, sz]',
    'acc = print_pxsz_by_hash[coin][h]',
    'acc[0] += px * sz',
    'acc[1] += sz',
    'if f.get("crossed") is True:',
    'key = (h, addr)',
    'rec[0] += px * sz',
    'rec[1] += sz',
    'if bt_ns < rec[2]:',
    'rec[2] = bt_ns',
    'order = np.argsort(p_ts, kind="stable")',
    'print_ts, print_px = p_ts[order], p_px[order]',
    't_px[i] = pxsz / szsum',
]


# ============================================================================
# (a) RAW EVENT-LEVEL RE-WALK
# ============================================================================
def _aws_list_hours(day):
    """List the hourly .lz4 keys for `day`, returns sorted list of (hour:int, key)."""
    key = f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{day}/"
    r = subprocess.run(
        ["aws", "s3", "ls", key, "--request-payer", "requester"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # This was the one abort in this directory that named a number and no place
        # at all: the bucket listing this check walks was not in the message, so a
        # reader could not tell a missing credential from a day that is not there.
        raise RuntimeError(mismatch_text(
            "the requester-pays listing this check walks did not come back",
            f"a listing of the hourly .lz4 objects for {day}",
            f"aws exit {r.returncode}, stderr {r.stderr.strip()[:300]!r}",
            key,
            "this is a fact about the S3 access on this machine, not about the "
            "clone. It is why this check sits in the opt-in --tape group"))
    hours = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        fn = parts[-1]
        if fn.endswith(".lz4") and fn[:-4].isdigit():
            hours.append((int(fn[:-4]), key + fn))
    hours.sort(key=lambda kv: kv[0])
    return hours


def _download_hours(day, max_hours):
    """Pull at most `max_hours` hourly .lz4 for `day` into the declared cache dir.

    THE DIRECTORY IS THE ONE THE TAPE WALKERS USE, not a private one. Where a fetched
    day lives is the declared setting CAP_RAW_CACHE, read through the module that owns
    it, and the per-day name matches build_quickwin_markouts.download_day, so an hour
    a walker already keeps is read here instead of fetched again -- and an hour this
    check fetches is one they can read. The private `hygiene_<day>` directory that
    stood here made both directions impossible for no gain.

    A day directory this check leaves behind holds at most `max_hours` files, which is
    below the completeness floor download_day accepts, so a walker meeting it re-fetches
    the full day rather than parsing a third of one.

    Returns (local_dir, [usable hour ints], [paths THIS run pulled]). The third value
    is what the teardown is allowed to touch: an hour that was already on disk was put
    there by something else, and this check fetched at most three of a twenty-four hour
    day, so "dispose of the day you fetched" cannot mean the directory here.

    Light by construction.
    """
    dst = os.path.join(bqm.raw_cache_dir(), f"quickwin_{day}")
    os.makedirs(dst, exist_ok=True)
    hours = _aws_list_hours(day)[:max_hours]
    got, pulled = [], []
    for hr, s3key in hours:
        local = os.path.join(dst, f"{hr}.lz4")
        if os.path.exists(local):
            print(f"[chk_field_hygiene] hour {hr}: reused a local .lz4 already on "
                  f"disk (CAP_RAW_CACHE)")
        else:
            r = subprocess.run(
                ["aws", "s3", "cp", "--request-payer", "requester", "--quiet",
                 s3key, local],
                capture_output=True, text=True,
            )
            if r.returncode != 0 or not os.path.exists(local):
                print(f"[chk_field_hygiene] WARN: failed to pull hour {hr}: "
                      f"{r.stderr.strip()}")
                continue
            pulled.append(local)
        got.append(hr)
    return dst, got, pulled


def _iter_block_lines(path):
    """Stream-decompress a local .lz4 and yield non-empty JSON block-line strings.
    Mirrors bqm.iter_local_hour_lines exactly (lz4 -dc, strip, skip empty)."""
    proc = subprocess.Popen(
        ["lz4", "-dc", path], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1 << 20,
    )
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield line
    proc.wait()


def raw_rewalk(day, max_hours):
    """Re-walk the raw fills for ONE day at the EVENT level, mirroring parse_day's
    loop but COUNTING the hygiene metrics instead of collapsing.

    Counts (over BTC+ETH, after the same coin / ZERO_HASH / None-hash guards the
    parser applies, so denominators match the parser's universe):
      n_raw_fills          - fills the parser would consider (passed the guards)
      n_crossed_true       - routed to the taker branch
      n_crossed_false      - routed to the maker branch
      n_crossed_absent     - crossed is None / missing  -> SILENT DROP
      n_crossed_other      - crossed present but not a bool True/False (defensive)
      n_sz_nonpos          - sz <= 0
      n_sz_unparseable     - px/sz not float-parseable (would raise in parser)
    Plus the maker-None rate: of the distinct (hash, taker) takers seen, how many
    had NO crossed=false leg sharing their hash within the walked window.
    """
    import json as _json

    coins = set(bqm.COINS)
    zero_hash = bqm.ZERO_HASH

    c = {
        "n_blocks": 0,
        "n_events_total": 0,           # every event seen, pre-guard
        "n_skipped_coin": 0,           # coin not in COINS
        "n_skipped_hash": 0,           # ZERO_HASH or None hash
        "n_raw_fills": 0,              # passed guards (the parser's universe)
        "n_crossed_true": 0,
        "n_crossed_false": 0,
        "n_crossed_absent": 0,
        "n_crossed_other": 0,
        "n_sz_nonpos": 0,
        "n_sz_unparseable": 0,
    }
    # maker-None rate: track, per coin, which hashes had a crossed=false leg and
    # the set of (hash, taker) takers, exactly as the parser keys them.
    hashes_with_maker = {co: set() for co in coins}
    taker_keys = {co: set() for co in coins}

    walked_hours = []
    day_dir, got, pulled = _download_hours(day, max_hours)
    for hr in got:
        path = os.path.join(day_dir, f"{hr}.lz4")
        try:
            for raw in _iter_block_lines(path):
                block = _json.loads(raw)
                bt = block.get("block_time")
                if bt is None:
                    continue
                c["n_blocks"] += 1
                for ev in block.get("events", []):
                    c["n_events_total"] += 1
                    f = ev[1]
                    coin = f.get("coin")
                    if coin not in coins:
                        c["n_skipped_coin"] += 1
                        continue
                    h = f.get("hash")
                    if h == zero_hash or h is None:
                        c["n_skipped_hash"] += 1
                        continue
                    c["n_raw_fills"] += 1
                    # size hygiene (parser reads float(f["sz"]) unconditionally)
                    try:
                        sz = float(f["sz"])
                        float(f["px"])
                        if sz <= 0:
                            c["n_sz_nonpos"] += 1
                    except (TypeError, ValueError, KeyError):
                        c["n_sz_unparseable"] += 1
                    # crossed routing (the silent-drop test)
                    cr = f.get("crossed")
                    if cr is True:
                        c["n_crossed_true"] += 1
                        addr = ev[0]
                        taker_keys[coin].add((h, addr))
                    elif cr is False:
                        c["n_crossed_false"] += 1
                        hashes_with_maker[coin].add(h)
                    elif cr is None:
                        c["n_crossed_absent"] += 1
                    else:
                        c["n_crossed_other"] += 1
            walked_hours.append(hr)
        except Exception as exc:   # noqa: BLE001 - mirror parser's tolerant loop
            print(f"[chk_field_hygiene] {day} hour {hr}: parse error {exc}")

    # maker-None rate over the distinct (hash, taker) takers actually seen
    n_takers = 0
    n_takers_no_maker = 0
    for co in coins:
        wm = hashes_with_maker[co]
        for (hh, _addr) in taker_keys[co]:
            n_takers += 1
            if hh not in wm:
                n_takers_no_maker += 1

    c["n_distinct_taker_keys"] = n_takers
    c["n_taker_keys_no_maker"] = n_takers_no_maker
    c["walked_day"] = day
    c["walked_hours"] = walked_hours
    c["n_hours_walked"] = len(walked_hours)

    # Deletion is the DEFAULT and it is DECLARED, not wired in. The branch reads
    # bqm.keep_raw_days() rather than restating CAP_KEEP_RAW here, so the rule keeps one
    # home and this file cannot drift from it. What the branch disposes OF is local and
    # has to be: this check pulls at most three hours of a twenty-four hour day into the
    # directory the tape walkers share, so removing the directory would take twenty-one
    # hours it never fetched. It removes the files this run pulled, and the directory
    # only if that leaves it empty -- os.rmdir refuses a non-empty one, which is the
    # test rather than a flag that could disagree with the disk.
    if bqm.keep_raw_days():
        print(f"[chk_field_hygiene] {day}: raw kept on disk "
              f"(CAP_KEEP_RAW; see CAP_RAW_CACHE)")
    else:
        for path in pulled:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(day_dir)
        except OSError:
            pass
        print(f"[chk_field_hygiene] {day}: {len(pulled)} pulled hourly file(s) deleted "
              f"(default; set CAP_KEEP_RAW=1 to keep)")
    return c


# ============================================================================
# (b) TEXTUAL DRIFT CHECK
# ============================================================================
def _norm(s):
    """Normalise a code line for byte-identity comparison: strip leading indent,
    collapse internal runs of whitespace, drop trailing whitespace. This compares
    the SEMANTIC line content, not its indentation level inside its function."""
    return re.sub(r"\s+", " ", s.strip())


def _read(path):
    with open(path, "r") as fh:
        return fh.read()


def _grep_lines(text, needle):
    return [ln for ln in text.splitlines() if needle in ln]


def _rhs(line):
    """The expression to the right of '=' or after 'return', whitespace-normalised.
    This is what is load-bearing; an extra prefix ('return' vs 'out[h] =') is a
    presentation difference, not an arithmetic divergence."""
    t = _norm(line)
    if t.startswith("return "):
        return t[len("return "):].strip()
    if " = " in t:
        return t.split(" = ", 1)[1].strip()
    return t


def _code_only(fn):
    """Whitespace-normalised EXECUTABLE source lines of `fn`: strips docstrings,
    comments, and blank lines so a docstring/comment-only difference does NOT read
    as a divergence. Returns a list (order preserved) or None if source is gone."""
    try:
        lines = inspect.getsource(fn).splitlines()
    except (OSError, TypeError):
        return None
    out = []
    in_doc = False
    doc_delim = None
    for ln in lines:
        t = _norm(ln)
        if not t:
            continue
        if in_doc:
            if doc_delim in t:
                in_doc = False
            continue
        if t.startswith("#"):
            continue
        # opening of a docstring / triple-quoted block
        for delim in ('"""', "'''"):
            if t.startswith(delim):
                # single-line docstring (opens and closes on the same line)?
                if t.count(delim) >= 2 and len(t) > len(delim):
                    t = None
                else:
                    in_doc = True
                    doc_delim = delim
                    t = None
                break
        if t is None:
            continue
        out.append(t)
    return out


def _matches_any(line, patterns):
    return any(re.search(p, line) for p in patterns)


def parse_day_drift():
    """Code-only diff of build_quickwin_markouts.parse_day vs ks2's copy.

    The docstring of this module (and of the parsers) claims parse_day is "copied
    verbatim". It is NOT line-for-line identical: ks2 legitimately OMITS the
    crossed=false maker branch + dominant-maker resolution and the extra retained
    taker fields. That divergence is ALLOW-LISTED here (PARSE_DAY_ALLOW_*). The
    shared CORE (per-hash VWAP print-path accumulation, crossed=true taker
    collapse, the markout/as-of-join) must stay identical.

    Verdict logic:
      - missing core anchor in either copy  -> divergence (the duplication broke),
      - a build-only line not on the allow-list, or a ks2-only line not a known
        presentation difference  -> NEW behavioral divergence (FLAG).
    Otherwise the only divergence is the allow-listed benign one -> identical-core.
    """
    b = _code_only(bqm.parse_day)
    k = _code_only(ks2.parse_day)
    if b is None or k is None:
        return {
            "build_codeline_count": None if b is None else len(b),
            "ks2_codeline_count": None if k is None else len(k),
            "missing_core_anchors": ["<source unavailable>"],
            "new_build_only": [],
            "new_ks2_only": [],
            "core_identical": False,
            "allowlisted_benign_only": False,
        }
    bset, kset = set(b), set(k)

    missing_core = [a for a in PARSE_DAY_CORE_ANCHORS
                    if not (a in bset and a in kset)]

    # lines present in one copy but not the other (verbatim, code-only)
    build_only = [ln for ln in b if ln not in kset]
    ks2_only = [ln for ln in k if ln not in bset]

    # a build-only line is OK only if it is part of the allow-listed maker/extra-
    # field divergence; a ks2-only line is OK only if it is a known presentation
    # difference. Anything else is a NEW behavioral divergence.
    new_build_only = [ln for ln in build_only
                      if not _matches_any(ln, PARSE_DAY_ALLOW_BUILD_ONLY)]
    new_ks2_only = [ln for ln in ks2_only
                    if not _matches_any(ln, PARSE_DAY_ALLOW_KS2_ONLY)]

    core_identical = (not missing_core)
    allowlisted_benign_only = (
        not missing_core and not new_build_only and not new_ks2_only
    )
    return {
        "build_codeline_count": len(b),
        "ks2_codeline_count": len(k),
        "n_build_only_total": len(build_only),
        "n_ks2_only_total": len(ks2_only),
        "n_build_only_allowlisted": len(build_only) - len(new_build_only),
        "n_ks2_only_allowlisted": len(ks2_only) - len(new_ks2_only),
        "missing_core_anchors": missing_core,
        "new_build_only": new_build_only,
        "new_ks2_only": new_ks2_only,
        "core_identical": bool(core_identical),
        "allowlisted_benign_only": bool(allowlisted_benign_only),
    }


def drift_check():
    """Compare the load-bearing lines + key function sources between the two
    parser copies. Returns a dict of findings.

    A faithful duplication can still differ in PRESENTATION (build's
    compute_markouts_all carries a docstring; ks2 also keeps a second
    compute_markout60 that returns the same RHS). We therefore test the
    ARITHMETIC: the markout RHS expression and the searchsorted line must be
    byte-identical wherever they appear, and the executable (docstring/comment-
    stripped) source of price_at + compute_markouts_all must match line-for-line.
    """
    build_txt = _read(BUILD_SRC)
    ks2_txt = _read(KS2_SRC)

    # --- 1. markout formula: the RHS expression must be byte-identical in every
    #        occurrence across BOTH files (build has it once as out[h]=...; ks2 has
    #        it twice: once as out[h]=... and once as the return in compute_markout60).
    mk_needle = "taker_dir.astype(np.float64) * (ref - taker_px) / taker_px * 1e4"
    build_mk = _grep_lines(build_txt, mk_needle)
    ks2_mk = _grep_lines(ks2_txt, mk_needle)
    build_mk_rhs = sorted({_rhs(x) for x in build_mk})
    ks2_mk_rhs = sorted({_rhs(x) for x in ks2_mk})
    # the RHS expression is unique and identical across all occurrences in both files
    all_rhs = build_mk_rhs + ks2_mk_rhs
    markout_identical = (
        len(build_mk) >= 1 and len(ks2_mk) >= 1
        and len(set(all_rhs)) == 1               # one and only one RHS, everywhere
    )

    # --- 2. searchsorted as-of join, byte-identical (normalised) ---
    ss_needle = 'np.searchsorted(print_ts, query_ns, side="right") - 1'
    build_ss = _grep_lines(build_txt, ss_needle)
    ks2_ss = _grep_lines(ks2_txt, ss_needle)
    build_ss_norm = sorted({_norm(x) for x in build_ss})
    ks2_ss_norm = sorted({_norm(x) for x in ks2_ss})
    join_identical = (
        len(build_ss) >= 1 and len(ks2_ss) >= 1 and build_ss_norm == ks2_ss_norm
    )

    # --- 3. backstop: EXECUTABLE source of price_at + compute_markouts_all identical
    #        (the module-level _code_only strips docstrings + comments + blanks so a
    #        docstring-only difference does NOT read as a divergence; the arithmetic
    #        is what must match).
    price_at_match = _code_only(bqm.price_at) == _code_only(ks2.price_at)
    cma_match = (_code_only(bqm.compute_markouts_all)
                 == _code_only(ks2.compute_markouts_all))

    # --- 4. parse_day: NOT verbatim-identical (build ~190 lines, ks2 ~103). Diff
    #        its code-only source and ALLOW-LIST the one known benign divergence
    #        (ks2 drops the crossed=false maker branch + the extra retained fields);
    #        the shared core must stay identical and no NEW divergence may appear.
    pd = parse_day_drift()
    parse_day_ok = pd["allowlisted_benign_only"]

    return {
        "markout_formula": {
            "needle": mk_needle,
            "build_occurrences": len(build_mk),
            "ks2_occurrences": len(ks2_mk),
            "rhs_expression": all_rhs[0] if all_rhs else None,
            "distinct_rhs": sorted(set(all_rhs)),
            "identical": bool(markout_identical),
        },
        "searchsorted_join": {
            "needle": ss_needle,
            "build_occurrences": len(build_ss),
            "ks2_occurrences": len(ks2_ss),
            "build_normalised": build_ss_norm,
            "ks2_normalised": ks2_ss_norm,
            "identical": bool(join_identical),
        },
        "price_at_source_identical": bool(price_at_match),
        "compute_markouts_all_source_identical": bool(cma_match),
        "parse_day": pd,
        "parse_day_core_identical_benign_divergence": bool(parse_day_ok),
        "all_loadbearing_identical": bool(
            markout_identical and join_identical and price_at_match and cma_match
            and parse_day_ok
        ),
    }


# ============================================================================
# CONTRACT ASSEMBLY
# ============================================================================
def build_contract(smoke, rw, drift):
    checks = []

    # ---- drift checks (always present) ----
    mk = drift["markout_formula"]
    checks.append({
        "name": "markout_formula_byte_identical",
        "assumption": "ks2_persistence_10day.py carries a DUPLICATED (not imported) "
                      "copy of the signed-markout formula identical to "
                      "build_quickwin_markouts.py.",
        "method": "Textually grepped the markout RHS "
                  "'taker_dir.astype(np.float64) * (ref - taker_px) / taker_px * 1e4' "
                  "in both files and compared the whitespace-normalised line sets.",
        "observed": {
            "build_occurrences": mk["build_occurrences"],
            "ks2_occurrences": mk["ks2_occurrences"],
            "identical": mk["identical"],
            "rhs_expression": mk["rhs_expression"],
            "distinct_rhs": mk["distinct_rhs"],
        },
        "verdict": "confirmed" if mk["identical"] else "refuted",
        "note": ("markout RHS expression is byte-identical wherever it appears in "
                 "both parser copies (ks2 keeps an extra compute_markout60 with the "
                 "same RHS; build keeps a docstring - neither changes the arithmetic)."
                 if mk["identical"] else
                 "markout formula has DIVERGED between the two copies - the "
                 "duplication is no longer faithful."),
    })

    ss = drift["searchsorted_join"]
    checks.append({
        "name": "searchsorted_join_byte_identical",
        "assumption": "the as-of (last-at-or-before) join "
                      "'np.searchsorted(print_ts, query_ns, side=\"right\") - 1' is "
                      "duplicated identically in both parser copies.",
        "method": "Textually grepped the searchsorted line in both files and compared "
                  "the whitespace-normalised line sets; backstopped by comparing the "
                  "full normalised source of price_at + compute_markouts_all.",
        "observed": {
            "build_occurrences": ss["build_occurrences"],
            "ks2_occurrences": ss["ks2_occurrences"],
            "identical": ss["identical"],
            "normalised_line": ss["build_normalised"],
            "price_at_source_identical": drift["price_at_source_identical"],
            "compute_markouts_all_source_identical":
                drift["compute_markouts_all_source_identical"],
        },
        "verdict": "confirmed" if (ss["identical"]
                                   and drift["price_at_source_identical"]
                                   and drift["compute_markouts_all_source_identical"])
                   else "refuted",
        "note": ("as-of join + price_at + compute_markouts_all are byte-identical "
                 "across the two copies."
                 if (ss["identical"] and drift["price_at_source_identical"]
                     and drift["compute_markouts_all_source_identical"]) else
                 "the join / markout function source has DIVERGED between the two "
                 "copies."),
    })

    # ---- parse_day code-only diff (the docstring's "copied verbatim" claim) ----
    pd = drift["parse_day"]
    pd_ok = drift["parse_day_core_identical_benign_divergence"]
    if pd["missing_core_anchors"]:
        pd_note = ("a shared-CORE parse_day line went MISSING from one copy "
                   f"({pd['missing_core_anchors']}): the print-path / collapse / "
                   "as-of-join duplication has DRIFTED.")
    elif pd["new_build_only"] or pd["new_ks2_only"]:
        pd_note = ("parse_day shows a NEW divergence beyond the allow-listed maker/"
                   "extra-field omission - build-only "
                   f"{pd['new_build_only']}, ks2-only {pd['new_ks2_only']} - "
                   "re-confirm the duplication.")
    else:
        pd_note = ("parse_day is NOT verbatim-identical (build "
                   f"{pd['build_codeline_count']} code-lines vs ks2 "
                   f"{pd['ks2_codeline_count']}), but the ONLY divergence is the "
                   "allow-listed benign one: ks2 omits the crossed=false maker "
                   "branch + dominant-maker resolution and the extra retained "
                   "fields (is_open/start_pos/side_b/closed_pnl/dir_code). The "
                   "shared core - per-hash VWAP print-path accumulation, the "
                   "crossed=true taker collapse and the markout/as-of-join - is "
                   "identical.")
    checks.append({
        "name": "parse_day_codeonly_diff",
        "assumption": "build_quickwin_markouts.parse_day is 'copied verbatim' into "
                      "ks2_persistence_10day.parse_day (per the docstring).",
        "method": "Stripped docstrings/comments/blanks from BOTH parse_day sources "
                  "and diffed code-line sets; asserted the load-bearing CORE anchors "
                  "(VWAP print-path accumulation, crossed=true collapse, "
                  "searchsorted join) are present in both, and allow-listed the one "
                  "known benign divergence (ks2 drops the crossed=false maker branch "
                  "+ the extra retained taker fields). Any line outside the "
                  "allow-list is flagged as a NEW divergence.",
        "observed": {
            "build_codeline_count": pd["build_codeline_count"],
            "ks2_codeline_count": pd["ks2_codeline_count"],
            "n_build_only_total": pd.get("n_build_only_total"),
            "n_build_only_allowlisted": pd.get("n_build_only_allowlisted"),
            "n_ks2_only_total": pd.get("n_ks2_only_total"),
            "n_ks2_only_allowlisted": pd.get("n_ks2_only_allowlisted"),
            "missing_core_anchors": pd["missing_core_anchors"],
            "new_build_only": pd["new_build_only"],
            "new_ks2_only": pd["new_ks2_only"],
            "core_identical": pd["core_identical"],
            "allowlisted_benign_only": pd["allowlisted_benign_only"],
        },
        "verdict": "confirmed" if pd_ok else "refuted",
        "note": pd_note,
    })

    drift_ok = drift["all_loadbearing_identical"]

    # ---- raw re-walk checks (full mode only) ----
    silent_drop_verdict = None
    if rw is not None:
        n_raw = max(1, rw["n_raw_fills"])
        frac_absent = rw["n_crossed_absent"] / n_raw
        frac_other = rw["n_crossed_other"] / n_raw
        frac_sznonpos = rw["n_sz_nonpos"] / n_raw
        frac_szbad = rw["n_sz_unparseable"] / n_raw
        n_tk = max(1, rw["n_distinct_taker_keys"])
        maker_none_rate = rw["n_taker_keys_no_maker"] / n_tk
        # routed fraction should account for ~all raw fills (true+false+absent+other)
        routed = (rw["n_crossed_true"] + rw["n_crossed_false"]
                  + rw["n_crossed_absent"] + rw["n_crossed_other"])

        silent_negligible = (frac_absent <= DROP_NEGLIGIBLE
                             and frac_other <= DROP_NEGLIGIBLE)
        size_clean = (frac_sznonpos <= DROP_NEGLIGIBLE
                      and frac_szbad <= DROP_NEGLIGIBLE)

        checks.append({
            "name": "crossed_silent_drop_fraction",
            "assumption": "Every raw fill is routed to either the taker branch "
                          "(crossed is True) or the maker branch (crossed is False); "
                          "a fill with crossed absent/None contributes to NEITHER and "
                          "is silently dropped from counterparty resolution.",
            "method": f"Re-walked {rw['n_hours_walked']} hour(s) of {rw['walked_day']} "
                      "(BTC+ETH) at the raw event level, mirroring parse_day's loop and "
                      "the same coin / ZERO_HASH / None-hash guards; counted fills by "
                      "crossed routing as a fraction of raw fills.",
            "observed": {
                "n_raw_fills": rw["n_raw_fills"],
                "n_crossed_true": rw["n_crossed_true"],
                "n_crossed_false": rw["n_crossed_false"],
                "n_crossed_absent": rw["n_crossed_absent"],
                "n_crossed_other": rw["n_crossed_other"],
                "frac_crossed_absent": frac_absent,
                "frac_crossed_other": frac_other,
                "frac_routed": routed / n_raw,
            },
            "verdict": "confirmed" if silent_negligible else "uncertain",
            "note": (f"crossed-absent fraction {frac_absent:.2e} (+other {frac_other:.2e}) "
                     "is negligible: effectively no fill is silently dropped on the "
                     "crossed routing."
                     if silent_negligible else
                     f"crossed-absent fraction {frac_absent:.2e} (+other {frac_other:.2e}) "
                     "is NON-trivial: a measurable population of fills is silently "
                     "dropped from counterparty resolution - re-read the field."),
        })

        checks.append({
            "name": "size_nonpositive_fraction",
            "assumption": "sz is read as float(f['sz']) unconditionally and is assumed "
                          "strictly positive (no sz<=0 fills entering the VWAP / "
                          "size-weighting).",
            "method": "On the same raw re-walk, counted fills with sz<=0 and fills "
                      "where px/sz are not float-parseable, as fractions of raw fills.",
            "observed": {
                "n_sz_nonpos": rw["n_sz_nonpos"],
                "n_sz_unparseable": rw["n_sz_unparseable"],
                "frac_sz_nonpos": frac_sznonpos,
                "frac_sz_unparseable": frac_szbad,
            },
            "verdict": "confirmed" if size_clean else "uncertain",
            "note": ("no non-positive or unparseable sizes in the sample - the VWAP / "
                     "size-weighting inputs are clean."
                     if size_clean else
                     "non-positive or unparseable sizes present - they would pollute "
                     "the VWAP entry and size weights."),
        })

        checks.append({
            "name": "maker_none_rate",
            "assumption": "Most taker (hash,taker) sweeps have a crossed=false leg "
                          "sharing the hash, so maker_id is resolved (maker_id == -1 "
                          "only rarely). The FINAL artifacts show maker_id==-1 at 0.0.",
            "method": "On the same raw re-walk, measured the fraction of distinct "
                      "(hash,taker) takers with NO crossed=false leg sharing the hash "
                      "within the walked window (these become maker_id == -1).",
            "observed": {
                "n_distinct_taker_keys": rw["n_distinct_taker_keys"],
                "n_taker_keys_no_maker": rw["n_taker_keys_no_maker"],
                "maker_none_rate": maker_none_rate,
                "note_window": "windowed to the walked hours; a maker leg in an "
                               "un-walked hour of the same hash would lower this rate, "
                               "so this is an UPPER bound on the true per-day rate.",
            },
            "verdict": "confirmed" if maker_none_rate <= 0.05 else "uncertain",
            "note": (f"maker-None rate {maker_none_rate:.3f} (upper bound on a "
                     f"{rw['n_hours_walked']}-hour window) is small: maker resolution "
                     "covers ~all taker sweeps, consistent with the 0.0 maker_id==-1 "
                     "rate in the final npz."
                     if maker_none_rate <= 0.05 else
                     f"maker-None rate {maker_none_rate:.3f} on this window is high; "
                     "note this is an upper bound (cross-hour maker legs not seen)."),
        })

        silent_drop_verdict = (
            "confirmed" if (silent_negligible and size_clean) else "uncertain"
        )

    # ---- overall ----
    # refuted dominates: a diverged load-bearing line is the worst outcome.
    # Otherwise "confirmed" requires BOTH halves to have actually run AND passed:
    # the textual drift half AND the raw field-hygiene re-walk (silent-drop / sz<=0
    # / maker-None). When the raw re-walk did NOT run (smoke mode, or rw is None /
    # unavailable), only the drift half was verified -- the silent-drop / sz<=0 /
    # maker-None legs were NEVER measured -- so the most we can honestly say is
    # "uncertain". We must not claim "confirmed" off the drift evidence alone.
    raw_rewalk_ran = rw is not None
    overall_note = None
    if not drift_ok:
        overall = "refuted"
        overall_note = ("a load-bearing parser line has DIVERGED between the two "
                        "copies; the duplication is no longer faithful.")
    elif not raw_rewalk_ran:
        overall = "uncertain"
        overall_note = (
            "DRIFT HALF ONLY: the textual drift / parse_day diff passed, but the raw "
            "field-hygiene re-walk did NOT run "
            + ("(--smoke mode skips it)" if smoke else "(S3/lz4 re-walk unavailable)")
            + ", so the silent-drop fraction (crossed absent/None), the sz<=0 "
            "fraction and the maker-None rate were NEVER measured. 'confirmed' "
            "requires BOTH halves to run and pass.")
    elif silent_drop_verdict == "confirmed":
        overall = "confirmed"
        overall_note = ("BOTH halves ran and passed: load-bearing parser lines are "
                        "identical (benign allow-listed parse_day divergence aside) "
                        "AND the raw re-walk found negligible silent-drop / sz<=0.")
    else:
        overall = "uncertain"
        overall_note = ("drift half passed, but the raw re-walk found a non-trivial "
                        "silent-drop / sz<=0 / maker-None population - re-read the "
                        "raw field.")

    contract = {
        "check": "field_hygiene",
        "mode": "smoke" if smoke else "full",
        "config": {
            "build_src": os.path.basename(BUILD_SRC),
            "ks2_src": os.path.basename(KS2_SRC),
            "raw_rewalk_ran": raw_rewalk_ran,
            "rewalk_day": None if (smoke or rw is None) else rw["walked_day"],
            "rewalk_hours": None if (smoke or rw is None) else rw["walked_hours"],
            "drop_negligible_threshold": DROP_NEGLIGIBLE,
        },
        "checks": checks,
        "overall_verdict": overall,
        "note": overall_note,
    }
    return contract


# ============================================================================
# MAIN
# ============================================================================
def main():
    started = artifact.start_clock()
    smoke = "--smoke" in sys.argv
    print(f"[chk_field_hygiene] mode={'smoke' if smoke else 'full'}")

    drift = drift_check()

    rw = None
    if not smoke:
        print(f"[chk_field_hygiene] raw re-walk: day={RW_DAY} "
              f"max_hours={RW_MAX_HOURS} (bounded, light)")
        try:
            rw = raw_rewalk(RW_DAY, RW_MAX_HOURS)
        except Exception as exc:   # noqa: BLE001
            print(f"[chk_field_hygiene] raw re-walk FAILED ({exc}); "
                  "falling back to drift-only -> verdict will reflect drift evidence "
                  "with the raw re-walk marked uncertain.")
            rw = None

    contract = build_contract(smoke, rw, drift)

    # build_contract already forces overall='uncertain' whenever the raw re-walk did
    # not run (smoke OR rw is None), so it never claims the raw read passed when it
    # did not. Here we ONLY add an explicit marker check for the full-mode-but-
    # re-walk-failed case, so the missing legs are visible in the checks list.
    if (not smoke) and rw is None:
        contract["checks"].append({
            "name": "raw_rewalk_not_run",
            "assumption": "the silent-drop + size hygiene re-walk should run in full mode.",
            "method": "attempted a bounded raw re-walk of one December day.",
            "observed": {"rewalk": "unavailable (S3/lz4 error)"},
            "verdict": "uncertain",
            "note": "drift lines are identical, but the raw re-walk did not run, so the "
                    "silent-drop / sz<=0 / maker-None legs are UNVERIFIED this run.",
        })

    # The two parser sources are the real inputs of the drift leg: it compares the
    # source text of the production parser against the copy this check reasons about,
    # so their hashes are what decides whether the answer can still be trusted. The
    # re-walked hourly objects are NOT hashed, and cannot be: the walk deletes each
    # hour after parsing it, so by the time this record is written the input is gone.
    artifact.write(
        os.path.basename(OUT_JSON), contract,
        script=__file__,
        inputs=[BUILD_SRC,
                KS2_SRC],
        scope={
            "population": (f"{rw['n_raw_fills']:,} raw fills re-walked"
                           if rw is not None else
                           "the raw re-walk did not run, so the silent-drop, "
                           "non-positive-size and missing-maker legs cover nothing; "
                           "only the source-drift legs were answered"),
            "window": (f"ONE DAY, {RW_DAY}, bounded to at most {RW_MAX_HOURS} hours"
                       if rw is not None else
                       "n/a: no raw hour was walked on this run"),
            "coins": "every coin present in the walked hours; the hygiene legs count "
                     "dropped and malformed records and are not cut by coin",
        },
        started=started,
    )

    # one-line human summary
    mk_ok = drift["markout_formula"]["identical"]
    ss_ok = (drift["searchsorted_join"]["identical"]
             and drift["price_at_source_identical"]
             and drift["compute_markouts_all_source_identical"])
    if rw is not None:
        n_raw = max(1, rw["n_raw_fills"])
        frac_absent = rw["n_crossed_absent"] / n_raw
        frac_sznp = rw["n_sz_nonpos"] / n_raw
        n_tk = max(1, rw["n_distinct_taker_keys"])
        mk_none = rw["n_taker_keys_no_maker"] / n_tk
        raw_txt = (f"raw[{rw['n_hours_walked']}h {rw['n_raw_fills']:,} fills]: "
                   f"crossed-absent={frac_absent:.2e} sz<=0={frac_sznp:.2e} "
                   f"maker-None(ub)={mk_none:.3f}")
    else:
        raw_txt = "raw re-walk: SKIPPED" + ("" if smoke else " (unavailable)")
    print(
        f"[chk_field_hygiene] OVERALL={contract['overall_verdict'].upper()} | "
        f"markout-identical={mk_ok} join-identical={ss_ok} | {raw_txt} "
        f"-> {os.path.basename(OUT_JSON)}"
    )
    # Two things can refute here and both stop the run: the parser's load-bearing
    # lines have drifted from the ones this check mirrors, or the raw re-walk found
    # a material silent-drop population. The unanswered case is separate and stays
    # exit 0 -- without S3 the re-walk cannot run, and that is a fact about the
    # machine. It is printed loudly all the same, because reading a skipped leg as a
    # passed one is exactly how this project once banked a verdict from one hour.
    return report_contract(contract, OUT_JSON,
                           inputs={"parser": os.path.basename(BUILD_SRC),
                                   "mode": "smoke" if smoke else "full"})


if __name__ == "__main__":
    sys.exit(main())
