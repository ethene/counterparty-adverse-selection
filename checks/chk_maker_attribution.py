"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: Zenodo 18184441 (Albers, Cucuringu, Howison, Shestopaloff,
           "An Open Book", 2026), SCHEMA.md Section 4 (Raw Book Diff Data);
           Hyperliquid node README (--write-raw-book-diffs); Zenodo
           trades_2025_12.tar side_info schema (Section 3).

CHECK: byte-verify whether RESTING orders on Hyperliquid L4 carry the order
OWNER's wallet attribution (maker-side identity) so an outsider can measure who
we COMPETE WITH on the book, not only who hits us.

WHY. The markout pipeline reads the maker only as a counterparty on a fill
(node_fills `crossed=false` leg). That answers "who trades against us." It does
NOT, by itself, establish that the standing book is owner-attributed -- i.e. that
the wallet behind every resting quote is observable before any trade. If resting
orders are owner-tagged, a maker-competition / queue-position layer (who quotes
where, who we sit behind) becomes feasible directly from the public data. This
script is the independent re-derivation that decides it on raw bytes.

WHAT IT VERIFIES on the raw `book_diffs_202512.tar` (Zenodo 18184441):
  (a) every book-diff record carries a `user` field,
  (b) `user` is a 40-hex Ethereum address (the resting-order owner),
  (c) the record key-set is exactly {user, oid, coin, side, px, raw_book_diff},
  (d) `raw_book_diff` is one of {"remove", {"new":...}, {"update":...}} and the
      `new` records (a fresh resting order placed on the book) are owner-tagged,
  (e) distinct owners per hour is plural (the book is many-maker, not a single
      anonymous aggregate),
  (f) CROSS-STREAM: the resting-order `oid` joins to the trade tape's
      `side_info[].oid`, and where it joins the trade-side `user` equals the
      book-diff `user` -- so a maker fill links back to the exact resting order
      and owner. This is the join that turns "who hits us" into "who we compete
      with on the book."

Independent: this script does NOT import the project parser or the Zenodo
read_data.py. It re-reads the raw tar member bytes and re-implements the walk, so
a bug in our pipeline cannot mask a bug here.

DATA FEASIBILITY (why this is cheap despite a 49.6 GB tar): book_diffs_202512.tar
is a sequential tar of per-hour gzip members. The FIRST data member sits at the
front of the file, so a single HTTP range request over the leading ~80 MB yields
one complete hour of book diffs (~5M records) without downloading the 49.6 GB
archive. The matching trade hour is read from the locally-held trades_2025_12.tar
(no network) when present; if absent the cross-stream leg (f) is skipped with a
SKIP verdict, not a FAIL.

Run command (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 checks/chk_maker_attribution.py
Override the trades tar location (defaults to the repo raw/ path):
  CAP_TRADES_TAR=/path/to/trades_2025_12.tar uv run --no-project --with-requirements requirements.txt \
      python3 checks/chk_maker_attribution.py
"""

import gzip
import json
import os
import re
import subprocess
import sys

ZENODO_BD_URL = (
    "https://zenodo.org/api/records/18184441/files/"
    "book_diffs_202512.tar/content"
)
# A tar member header is 512 bytes; name at offset 0 (100 b), octal size at 124 (12 b).
# The first data member of book_diffs_202512.tar is the first hour's exNN.gz; a
# ranged read of the leading PREFIX_BYTES captures its 512-byte header so the exact
# member offset+size can be read, then the member itself is range-fetched.
PREFIX_BYTES = 8192          # enough for the leading tar headers
RANGE_PAD = 64 * 1024        # safety pad when fetching the member

HEX_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
EXPECTED_KEYS = {"user", "oid", "coin", "side", "px", "raw_book_diff"}

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))
import artifact                                                          # noqa: E402
from evidence import mismatch_text, report_verdicts                      # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_maker_attribution_results.json")

# What each verdict ASSERTS, in words, so a failure says what was expected and not
# only which name went false. This check is the one that taught the lesson: it came
# back non-zero inside the common runner with the single line "one or more verdicts
# FAILED (see JSON)", and the cause could only be found by running it again by hand.
EXPECTATIONS = {
    "every_record_has_user": "every book-diff record carries a `user` field, because "
                             "the claim under test is that an outsider can see the "
                             "owner of a resting order at all",
    "user_is_hex_owner_address": "every `user` is a 40-hex Ethereum address, so the "
                                 "field identifies an owner rather than an internal "
                                 "index",
    "keyset_is_user_oid_coin_side_px_rawdiff": "the record key-set is exactly "
                                               "{user, oid, coin, side, px, "
                                               "raw_book_diff}; a different key-set "
                                               "means the schema moved under us",
    "difftypes_are_new_remove_update": "every raw_book_diff is one of new, remove or "
                                       "update, with no OTHER bucket",
    "new_resting_orders_are_owner_tagged": "every freshly placed resting order is "
                                           "owner-tagged, which is what makes queue "
                                           "position attributable before any trade",
    "book_is_many_owner_not_aggregate": "the hour carries at least two distinct "
                                        "owners, so the book is many-maker rather "
                                        "than one anonymous aggregate",
    "cross_stream_oid_owner_match": "where a resting oid joins the trade tape's "
                                    "side_info, the owner address matches on every "
                                    "join: this is the link that turns who hits us "
                                    "into who we compete with on the book",
    "OUTSIDER_CAN_SEE_RESTING_ORDER_OWNER": "all six core legs hold together",
    # Carries a WORD, not a boolean, and the word distinguishes three states that a
    # boolean folded into two: every leg ran and held (ALL_PASS), a leg ran and did
    # not hold (FAIL), and a leg could not run at all (UNCERTAIN). The third used to
    # be reported as the first.
    "OVERALL": "the core legs and the cross-stream leg both RAN and both hold",
}

DEFAULT_TRADES_TAR = os.path.normpath(
    os.path.join(HERE, "..", "..", "02_data", "raw", "trades_2025_12.tar")
)
TRADES_TAR = os.environ.get("CAP_TRADES_TAR", DEFAULT_TRADES_TAR)


def _curl_range(url, start, end):
    """Return the raw bytes for an HTTP byte range [start, end] (inclusive).

    A failure here says nothing about the repository, so it says what it DOES mean
    instead: which range of which archive was asked for, what curl returned, and how
    many bytes came back. The previous message printed 200 characters of stderr and
    nothing else, and an empty body from a ranged request -- which is what actually
    happened, and what moved this check into the opt-in network group -- produced a
    failure that named neither the range nor the fact that the body was empty.
    """
    r = subprocess.run(
        ["curl", "-s", "-w", "%{http_code}", "-o", "/dev/stdout",
         "-H", f"Range: bytes={start}-{end}", url],
        capture_output=True,
    )
    body = r.stdout[:-3] if len(r.stdout) >= 3 else b""
    status = r.stdout[-3:].decode("ascii", "replace") if r.stdout else "none"
    if r.returncode != 0 or not body:
        raise SystemExit(mismatch_text(
            "the archive did not return the bytes this check reads",
            f"{end - start + 1:,} bytes of a byte-range request",
            f"{len(body):,} bytes, curl exit {r.returncode}, HTTP status {status}, "
            f"stderr {r.stderr[:200]!r}",
            f"range {start}-{end} of {url}",
            "this is a fact about the remote archive, not about the clone. It is "
            "why this check sits in the opt-in --network group"))
    return body


def _first_member_offset_size(prefix):
    """Walk the leading tar headers; return (name, data_offset, size) of the first
    non-empty regular file member (a *.gz hour of book diffs)."""
    off = 0
    seen = []          # every header walked, so a failure can say what WAS there
    while off + 512 <= len(prefix):
        hdr = prefix[off:off + 512]
        name = hdr[0:100].split(b"\x00")[0].decode("utf-8", "replace")
        if not name.strip():
            break
        try:
            size = int(hdr[124:136].split(b"\x00")[0].strip(), 8)
        except ValueError:
            size = 0
        if name.endswith(".gz") and size > 0:
            return name, off + 512, size
        seen.append(f"{name or '(blank header)'} size={size:,}")
        off += 512 + ((size + 511) // 512) * 512
    raise SystemExit(mismatch_text(
        "the tar prefix holds no hourly book-diff member to read",
        f"a *.gz member with a non-zero size in the first {len(prefix):,} bytes of "
        f"the archive",
        f"{len(seen)} tar header(s), none of them a non-empty .gz: "
        f"{'; '.join(seen[:8]) if seen else '(no readable header at all)'}",
        f"the leading {len(prefix):,} bytes of {ZENODO_BD_URL}",
        "either the archive's member layout moved, or PREFIX_BYTES is now too "
        "small to reach the first member. This is a fact about the remote "
        "archive, not about the clone"))


def _fetch_first_bookdiff_hour():
    """Range-fetch + gunzip the first hourly book-diff member; return (name, text)."""
    print(f"[chk_maker] HEAD prefix of {ZENODO_BD_URL}")
    prefix = _curl_range(ZENODO_BD_URL, 0, PREFIX_BYTES - 1)
    name, data_off, size = _first_member_offset_size(prefix)
    print(f"[chk_maker] first member {name!r} data_off={data_off} size={size:,}")
    member = _curl_range(ZENODO_BD_URL, data_off, data_off + size - 1)
    if len(member) != size:
        # ranged servers can clip; accept a short read only if it still gunzips
        print(f"[chk_maker] WARN short read {len(member):,} != {size:,}")
    text = gzip.decompress(member).decode("utf-8", "replace")
    return name, text


def _read_trade_hour(date_folder, hour):
    """Read one trade hour from the LOCAL trades tar; return list of dicts or None
    if the tar is absent (cross-stream leg then SKIPs, does not FAIL)."""
    if not os.path.exists(TRADES_TAR):
        return None
    member = f"{date_folder}/{hour}.gz"
    r = subprocess.run(
        ["tar", "xf", TRADES_TAR, "-O", member],
        capture_output=True,
    )
    if r.returncode != 0 or not r.stdout:
        return None
    text = gzip.decompress(r.stdout).decode("utf-8", "replace")
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def main():
    started = artifact.start_clock()
    name, bd_text = _fetch_first_bookdiff_hour()
    # member name looks like "20251201/ex22.gz" -> date_folder "20251201", hour "22"
    m = re.match(r"(\d{8})/ex(\d{1,2})\.gz$", name)
    date_folder = m.group(1) if m else None
    hour = m.group(2) if m else None

    n = 0
    user_present = 0
    user_hex = 0
    keyset_ok = True
    bad_keysets = {}
    diff_types = {}
    coins = {}
    owners = set()
    new_owner_tagged = 0
    new_total = 0
    oid_owner = {}                 # resting oid -> owner wallet
    samples = {"new": None, "remove": None, "update": None}

    for line in bd_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        n += 1
        ks = frozenset(r.keys())
        if ks != EXPECTED_KEYS:
            keyset_ok = False
            key = ",".join(sorted(r.keys()))
            bad_keysets[key] = bad_keysets.get(key, 0) + 1
        u = r.get("user")
        if "user" in r:
            user_present += 1
        if isinstance(u, str) and HEX_ADDR.match(u):
            user_hex += 1
            owners.add(u)
        oid = r.get("oid")
        if oid is not None and u is not None:
            oid_owner[oid] = u
        coins[r.get("coin")] = coins.get(r.get("coin"), 0) + 1
        rbd = r.get("raw_book_diff")
        if rbd == "remove":
            dt = "remove"
        elif isinstance(rbd, dict) and "new" in rbd:
            dt = "new"
            new_total += 1
            if isinstance(u, str) and HEX_ADDR.match(u):
                new_owner_tagged += 1
        elif isinstance(rbd, dict) and "update" in rbd:
            dt = "update"
        else:
            dt = "OTHER"
        diff_types[dt] = diff_types.get(dt, 0) + 1
        if samples.get(dt) is None and dt in samples:
            samples[dt] = line[:300]

    # ---- cross-stream leg (f): resting oid -> trade side_info oid + owner match ----
    trades = _read_trade_hour(date_folder, hour) if date_folder else None
    cross_done = trades is not None
    join_hit = 0
    join_miss = 0
    owner_match = 0
    if cross_done:
        for t in trades:
            for si in t.get("side_info", []):
                oid = si.get("oid")
                usr = si.get("user")
                if oid in oid_owner:
                    join_hit += 1
                    if oid_owner[oid] == usr:
                        owner_match += 1
                else:
                    join_miss += 1

    # ---- verdicts ----
    v_user_present = user_present == n and n > 0
    v_user_hex = user_hex == n and n > 0
    v_keyset = keyset_ok and n > 0
    v_difftypes = set(diff_types) <= {"new", "remove", "update"} and diff_types.get("OTHER", 0) == 0
    v_new_tagged = new_total > 0 and new_owner_tagged == new_total
    v_many_owners = len(owners) >= 2
    # cross-stream: where a resting oid joins, the owner address must match 100%
    if cross_done:
        v_cross = join_hit > 0 and owner_match == join_hit
        cross_status = "PASS" if v_cross else "FAIL"
    else:
        v_cross = True                # not a failure; the local trades tar is absent
        cross_status = "SKIP (local trades tar absent; set CAP_TRADES_TAR)"

    core_pass = all([v_user_present, v_user_hex, v_keyset, v_difftypes,
                     v_new_tagged, v_many_owners])
    # THE WORD SAYS WHICH LEGS RAN, NOT ONLY WHETHER THE ONES THAT RAN AGREED. Above,
    # a cross-stream leg that could not run is scored True, which is right -- an
    # archive that is not on this machine is not evidence against the repository. But
    # `all_pass` then carried that True into the word ALL_PASS, and ALL_PASS says
    # something the run did not establish: on a machine without the trades archive
    # this gate declared a full pass over a population one leg short. The skip is
    # stated in `cross_status` and printed on the screen, so the failure was never a
    # hidden one -- it was hidden from the only reader that matters here, the runner,
    # which reads the word and nothing else.
    #
    # UNCERTAIN is the word this repository already uses for a question that could not
    # be asked, and checks/run_all_checks.py lists it in UNANSWERED_WORDS, so the
    # battery files this run under "did not answer" instead of under "passed". A core
    # failure still outranks it: a leg that ran and disagreed is news, and news is not
    # softened by another leg having been skipped.
    if not core_pass:
        verdict_word = "FAIL"
    elif cross_done:
        verdict_word = "ALL_PASS" if v_cross else "FAIL"
    else:
        verdict_word = "UNCERTAIN"

    results = {
        # ONE VERDICT WORD AT THE TOP, beside the nine it is made of. This file
        # carried the nine and no summary, so a reader -- and the runner, which greps
        # the screen for a verdict word -- had to know which of the nine names meant
        # the whole. The word is `all_pass` in a different shape and moves no number.
        # The time it was taken comes from _meta.run, which artifact.write stamps.
        "verdict": verdict_word,
        "_meta": {
            "check": "raw maker/resting-order owner-attribution byte-verify "
                     "(can an outsider see the resting-order owner on Hyperliquid L4?)",
            "author": "Dmitry Stakhin",
            # RENAMED from `date`. It is the day this check was written, not the day
            # the verdict below was taken; the two sat under one name and the older
            # one read as the newer. When the verdict was taken is _meta.run.
            "first_written": "2026-06-22",
            "book_diff_source": ZENODO_BD_URL,
            "book_diff_member": name,
            "trades_source": (os.path.basename(TRADES_TAR) if cross_done
                              else "(absent)"),
            "independent": "raw tar-member re-walk; does NOT import the project "
                           "parser or the Zenodo read_data.py",
            "expected_keys": sorted(EXPECTED_KEYS),
            "schema_ref": "Zenodo 18184441 SCHEMA.md Section 4: 'user = Ethereum "
                          "address of the order owner'",
        },
        "counts": {
            "records_in_hour": n,
            "user_field_present": user_present,
            "user_hex_valid": user_hex,
            "distinct_resting_owners": len(owners),
            "diff_types": diff_types,
            "coins": coins,
            "new_orders": new_total,
            "new_orders_owner_tagged": new_owner_tagged,
            "bad_keysets": bad_keysets,
            "cross_stream": {
                "performed": cross_done,
                "resting_oid_joins_to_trade_side_info": join_hit,
                "trade_side_info_no_resting_oid_taker_or_same_block": join_miss,
                "owner_address_matches_on_join": owner_match,
            },
        },
        "verdicts": {
            "every_record_has_user": bool(v_user_present),
            "user_is_hex_owner_address": bool(v_user_hex),
            "keyset_is_user_oid_coin_side_px_rawdiff": bool(v_keyset),
            "difftypes_are_new_remove_update": bool(v_difftypes),
            "new_resting_orders_are_owner_tagged": bool(v_new_tagged),
            "book_is_many_owner_not_aggregate": bool(v_many_owners),
            "cross_stream_oid_owner_match": cross_status,
            "OUTSIDER_CAN_SEE_RESTING_ORDER_OWNER": bool(core_pass),
            "OVERALL": verdict_word,
        },
        "samples": samples,
    }

    # Two inputs of different kinds. The Zenodo URL is kept whole, because the record
    # and the byte range ARE the identity of what was read and nothing local appears
    # in it; the trades tar is a local file and is hashed when it is present. The
    # cross-stream leg is skipped when it is absent, so present=false on it is what
    # says WHY that leg did not run.
    artifact.write(
        os.path.basename(OUT_JSON), results,
        script=__file__,
        inputs=[ZENODO_BD_URL, TRADES_TAR],
        scope={
            "population": f"{n:,} book-diff records of one hourly member, "
                          f"{len(owners):,} distinct resting owners in it",
            "window": f"ONE HOUR: member {name}. The verdict is about that hour, not "
                      f"about the whole archive",
            "coins": sorted(coins) if coins else "no coin appeared in this member",
        },
        started=started,
        # Same rule as the other gates: a run whose cross-stream leg could not run at
        # all leaves the record of a run whose did.
        answered=(verdict_word != "UNCERTAIN"),
    )

    print("\n" + "=" * 80)
    print("MAKER / RESTING-ORDER OWNER-ATTRIBUTION BYTE-VERIFY - SUMMARY")
    print("=" * 80)
    print(f"  member: {name}   records: {n:,}")
    print(f"  user present: {user_present:,}/{n:,}   hex-valid: {user_hex:,}/{n:,}")
    print(f"  distinct resting owners this hour: {len(owners):,}")
    print(f"  diff_types: {diff_types}")
    print(f"  new resting orders owner-tagged: {new_owner_tagged:,}/{new_total:,}")
    if cross_done:
        print(f"  cross-stream: resting oid joins to trade side_info: {join_hit:,}; "
              f"owner matches on join: {owner_match:,}/{join_hit:,}; "
              f"takers/same-block (no rest): {join_miss:,}")
    else:
        print("  cross-stream: SKIPPED (local trades tar absent)")
    print("-" * 80)
    for k, v in results["verdicts"].items():
        flag = v if isinstance(v, str) else ("PASS" if v else "FAIL")
        print(f"  {flag if isinstance(v, str) else ('PASS' if v else 'FAIL')}  {k}")
    print("=" * 80)
    print(f"  wrote {os.path.basename(OUT_JSON)}")
    # This is the line that named the rule. Until now it raised SystemExit with the
    # single sentence "one or more verdicts FAILED (see JSON)": which verdict, what
    # it asserts and the counts it was taken from were all written to the file and
    # none of it reached the screen, so the only way to learn the cause was to run
    # the check a second time by hand. EXPECTATIONS above supplies the words, the
    # counts block supplies the numbers, and report_verdicts fails on exactly the
    # same condition -- every core leg is in this map, so a false verdict here and
    # `not all_pass` are the same event.
    return report_verdicts(results["verdicts"], EXPECTATIONS, OUT_JSON,
                           inputs={"book_diff_member": name,
                                   "book_diff_source": ZENODO_BD_URL,
                                   "trades_tar": (os.path.basename(TRADES_TAR)
                                                  if cross_done else "(absent)")},
                           counts=results["counts"])


if __name__ == "__main__":
    sys.exit(main())
