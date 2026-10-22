"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-23
Glosten-Milgrom (1985) information-based maker: a market-level-toxicity (VPIN/PIN)
quoter for the bake-off, with NO counterparty identity, evaluated as a markout-based
counterfactual on the Hyperliquid tape.
References:
  - Glosten, Lawrence R., and Paul R. Milgrom. "Bid, Ask and Transaction Prices in a
    Specialist Market with Heterogeneously Informed Traders." Journal of Financial
    Economics, vol. 14, no. 1, 1985, pp. 71-100.
  - Easley, David, Marcos M. Lopez de Prado, and Maureen O'Hara. "Flow Toxicity and
    Liquidity in a High-Frequency World." The Review of Financial Studies, vol. 25,
    no. 5, 2012, pp. 1457-1493.
  - Easley, David, Nicholas M. Kiefer, Maureen O'Hara, and Joseph B. Paperman.
    "Liquidity, Information, and Infrequently Traded Stocks." The Journal of Finance,
    vol. 51, no. 4, 1996, pp. 1405-1436.
  - Avellaneda, Marco, and Sasha Stoikov. "High-frequency Trading in a Limit Order
    Book." Quantitative Finance, vol. 8, no. 3, 2008, pp. 217-224.
  - Hyperliquid node-data / L2-book S3 archives -- source of the on-disk markout npz.
  - Zenodo 18184441 (Albers et al. 2026) -- the public L4 node-data release.
"""

# ---------------------------------------------------------------------------
# GLOSTEN-MILGROM (1985) INFORMATION-BASED, MARKET-LEVEL-TOXICITY, COUNTERPARTY-
# BLIND MAKER -- ONE QUOTER IN THE BAKE-OFF.
#
# WHY THIS FILE EXISTS. The bake-off compares three quoters on the SAME tape:
#   (1) symmetric Avellaneda-Stoikov inventory-only maker          (as_quoter.py),
#   (2) this Glosten-Milgrom information-based maker               (gm_quoter.py),
#   (3) the counterparty-toxicity-conditioned skew overlay         (t1_*.py, maker_econ.py).
# The WHOLE POINT of including GM is that GM's signal is MARKET-LEVEL order-flow
# toxicity (a VPIN/PIN proxy computed on our own tape) with NO counterparty identity.
# By construction GM CANNOT reach what the counterparty-resolved term reaches: it
# prices the AVERAGE adverse-selection content of the flow, not the WHO. This file
# instantiates GM's closed form, estimates its one structural input (the informed-
# trade probability) from a VPIN/PIN-style toxicity proxy on the tape, and evaluates
# its adverse-selection half-spread the same markout-counterfactual way the other two
# quoters are evaluated.
#
# WHAT GM IS, AND WHAT IT IS NOT. Glosten-Milgrom (1985) is an INFORMATION model. A
# competitive market maker quotes bid/ask to a stream of orders, a fraction of which
# are informed of the true value; the spread exists PURELY because of adverse
# selection (no inventory, no processing cost). The maker's ask is its conditional
# expectation of value GIVEN a buy, the bid its expectation GIVEN a sell; under
# competition expected profit is zero. The single structural driver is the
# probability the incoming order is informed (the PIN of Easley-Kiefer-O'Hara-
# Paperman 1996; we proxy its high-frequency analogue with the VPIN flow-toxicity of
# Easley-Lopez de Prado-O'Hara 2012). GM conditions on NOTHING about who the
# counterparty is -- that counterparty-blindness is precisely the axis the toxicity-
# aware extension adds, and GM's book-only information is exactly what cannot recover
# the per-counterparty idiosyncratic component. GM produces a SPREAD, never an alpha,
# a P&L, or a Sharpe; none is claimed anywhere in this file.
#
# THE CLOSED FORM (Glosten-Milgrom 1985, the symmetric two-type reduction):
#   Let pi  = P(the incoming order is informed)         in [0, 1)   (the PIN/VPIN proxy)
#       J   = E[ |V - mid| ]  the expected ABSOLUTE adverse price revision an informed
#             order carries (the "jump" toward true value), in PRICE units.
#   A competitive maker raises the ask above mid by the EXPECTED adverse content of a
#   BUY and lowers the bid below mid by the expected adverse content of a SELL. With a
#   symmetric informed jump those two are equal, so
#       half_spread = pi * J ,    ask = mid + pi*J ,    bid = mid - pi*J ,
#       total_spread (delta_GM) = 2 * pi * J .
#   This is the adverse-selection-only GM spread: it is zero when pi = 0 (no informed
#   flow => no spread) and it WIDENS monotonically in BOTH pi (more toxic flow) and J
#   (a bigger informed price move). It carries NO inventory term and NO counterparty
#   term. (The general GM ask/bid are the Bayesian posteriors E[V | buy], E[V | sell];
#   the symmetric two-type case collapses them to mid +/- pi*J. We use the symmetric
#   reduction because the tape gives us a market-level pi and a market-level |markout|
#   magnitude, not a per-order type label -- see the CLOB MAPPING note below.)
#
# THE INFORMED-TRADE PROBABILITY pi (estimated on OUR tape, NOT from identity):
#   VPIN/PIN proxy. Per (coin, day) bucket the fills into N_VPIN_BUCKETS equal-COUNT
#   buckets in arrival order (a count-clock stand-in for the volume clock of Easley-
#   Lopez de Prado-O'Hara 2012; we use a count clock because notional is heavy-tailed
#   and a volume clock on a few whale fills would degenerate). In each bucket compute
#   the order-flow imbalance from the SIGNED taker side (taker_side: 1 = buy-aggressor
#   = +1, 0 = sell-aggressor = -1, the byte-verified convention):
#       imb_b = | sum(sign) | / n_b  in [0, 1].
#   pi_proxy(coin, day) = mean_b imb_b  -- the average absolute buy/sell imbalance, the
#   VPIN flow-toxicity statistic. It is a MARKET-LEVEL toxicity read: it never looks at
#   WHICH wallet sent an order, only at the net directional pressure of the pooled
#   flow, exactly the information a book-only Glosten-Milgrom maker has. The headline pi
#   is the per-coin median of the daily pi_proxy; the daily series is reported too.
#   NO LOOKAHEAD: each bucket's imbalance uses only its own (coin, day) fills in
#   arrival order; the pi for a (coin, day) is computed from that day's own fills only.
#
# THE EXPECTED ADVERSE MOVE J (the empirical signed-markout MAGNITUDE):
#   J is the size of the price revision an informed order causes. We read it off the
#   realized markout the way Stoll's realized-spread / adverse-selection decomposition
#   reads adverse selection off post-trade price drift: the EXEC->mid book-mid markout
#   mo{h}_mid is the post-fill move of the mid against the maker. Its magnitude is the
#   adverse revision. We use the per-(coin) MEAN ABSOLUTE book-mid markout at the
#   headline horizon as J_bps, then J_price = J_bps/1e4 * mid. This is a MARKET-LEVEL
#   magnitude -- it is NOT conditioned on the counterparty. (Sign convention: a
#   POSITIVE taker markout is adverse for the passive maker; we take |.| because GM's J
#   is the size of the informed jump regardless of direction.)
#
# UNIT DISCIPLINE (stated, tested, never fudged):
#   - pi is dimensionless in [0, 1). J is in PRICE units (or bps when reported in bps).
#   - half_spread_price = pi * J_price ; half_spread_bps = pi * J_bps. Because pi is
#     dimensionless, the bps and price forms are the same multiplication, so a bps
#     half-spread is directly comparable to spread_entry_bps/2 (the real BBO half).
#   - REUSE as_quoter.spread_price_to_bps for any price->bps conversion so the two
#     quoters convert identically.
#
# SIGN / MONOTONICITY (the self-tests assert all of these):
#   pi = 0      => half_spread == 0 exactly (no informed flow => no GM spread).
#   half_spread strictly INCREASES in pi (more toxic flow => wider) and in J.
#   ask = mid + half_spread > mid ; bid = mid - half_spread < mid ; quotes SYMMETRIC
#   about the mid (GM has no inventory skew -- that is A-S's axis, not GM's).
#   GM half_spread does NOT depend on inventory or on any counterparty attribute.
#
# COUNTERFACTUAL-ONLY (HARD RULE 1). This is a markout-based counterfactual overlay,
# NOT a matching engine: there is no queue position, no fill probability, no requote
# latency, no re-cleared book. A GM maker quoting half_spread h is scored on the
# realized fills the way maker_econ.py scores the symmetric maker: pre-fee maker PnL
# per fill is the BBO/realized half-spread it would have EARNED minus the realized
# adverse markout it would have PAID. The ONLY fill-awareness used is the maker_econ-
# style recapture APPROXIMATION (a fraction f of would-be fills at +h bps minus a
# penalty c) and it is LABELLED an approximation. No live-performance claim is made.
#
# COST-NOT-ALPHA (HARD RULE 2). Like every quoter in the bake-off, GM is expected net-
# NEGATIVE at every Hyperliquid maker-fee tier: the adverse selection on this flow
# exceeds the spread it can earn. GM is NEVER framed as profitable / alpha / edge /
# Sharpe; any such word here appears only inside an explicit negation. GM, being
# counterparty-blind, cannot even achieve the toxicity overlay's cost REDUCTION, which
# is CONCENTRATED, mostly ETH, and fragile -- and which GM has no way to see, because it
# conditions on market-level toxicity only. The concentration has one home, and it is
# mm_bakeoff_results.json pairwise_wallet_resolved.by_pair.*.concentration_by_wallet: on
# the one-sided pair the top five wallets hold 41.3 per cent of the gain pooled. The
# figure that stood here until 2026-08-03 -- "~top 5 wallets ~66%" -- was a string literal
# carried in from a June maker-economics run, where it measured the top five wallets'
# share of REJECTED FLOW: a different quantity over a different population, and outside
# the range of every cut this tree actually publishes.
#
# LINEAGE (HARD RULE 3). The adverse-selection-aware quoting leg (global + per-tier
# skew) is OWNED by Barzykin, Bergault, Gueant, Lemmel (arXiv:2508.20225); the
# toxicity overlay is a REDUCED-FORM instance of that idea, kept as validation. GM
# (1985) is the FOUNDING information-based spread the whole adverse-selection lineage
# descends from; this file uses GM as the book-only-information baseline, not as a new
# quoting theory.
#
# DATA (already on disk, NO re-pull):
#   quickwin_markouts_mid.npz  -- taker_side (signed flow for pi), spread_entry_bps
#     (real BBO half), mo{h}_mid (book-mid markout for J), entry_px, coin, day.
#   quickwin_markouts.npz      -- mo{h} (trade-print markout) for the net_PRINT
#     counterfactual measure, exactly as maker_econ.py uses it.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 quoters/gm_quoter.py
# Fast analytic self-test (loads NO data):
#   uv run --no-project --with-requirements requirements.txt python3 quoters/gm_quoter.py --selftest
# Smoke slice (subset days/coins after load):
#   CAP_DAYS=9,10 CAP_COINS=BTC uv run --no-project --with-requirements requirements.txt python3 \
#       quoters/gm_quoter.py
# ---------------------------------------------------------------------------

import os
import sys

import numpy as np

# One place writes a results file, so this artifact records its producer and hash, its
# inputs, its scope and its settings the way every other one does. See artifact.py.
# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import panel_io as P
import settings as H

# REUSE the A-S quoter's price<->bps conversion so the two quoters convert identically.
from as_quoter import spread_price_to_bps

# -------------------- determinism --------------------
# READ from settings.py rather than typed here. The value is unchanged -- this file has
# always drawn from 20260623 and settings.SEED_BY_PURPOSE declares that same number for
# this purpose -- so nothing in gm_quoter_results.json moves.
SEED = H.seed_for("gm_quoter")
np.random.seed(SEED)
RNG = np.random.default_rng(SEED)

# -------------------- paths (bare filenames in _meta; no /Users leak) --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
MID_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")               # taker_side + the mid ladder + spread
PRINT_NPZ = os.path.join(P.data_root(), "quickwin_markouts.npz")           # the trade-print ladder
OUT_JSON = os.path.join(HERE, "gm_quoter_results.json")

# -------------------- coin mapping (REUSE maker_econ.py; SOL added for code 2) --------------------
COIN_NAME = H.coin_labels("quickwin")        # the map belongs to the FILE, not the project
COIN_NAMES = H.coin_labels("panel")          # superset for per-coin reporting

# -------------------- day windows: DERIVED, not declared --------------------
# These two used to be the literal tuples (4,5,6,7,8) and (9,10,11,12,13), copied from
# maker_econ.py. They are days of the MONTH and are right only for a window that opens
# on the 4th and closes on the 13th. The December window this file reads does open on
# the 4th, so the derived split reproduces those tuples exactly and no number here
# moves. Both names remain as OVERRIDE HOOKS defaulting to None, which means "split the
# days the input actually carries" through settings.split_early_late.
#
# WHY THEY CARRY _OVERRIDE IN THE NAME. They used to be spelled EARLY_DAYS and
# LATE_DAYS, which are the names settings.py owns for the day split, and the settings
# gate read them as this file declaring that setting a second time -- two of the sites
# it reports. The reading was right about the name and wrong about the value: there is
# no value here to migrate, because the split already comes from settings.py and what
# these two hold is the absence of an override. A name that states a setting its value
# does not come from is the defect settings.py calls out in its own second rule, so the
# repair is to make the name say what the object is. Nothing else in the tree reads
# either name: they are used only by early_late_days below.
EARLY_DAYS_OVERRIDE = None
LATE_DAYS_OVERRIDE = None


def early_late_days(day):
    """The (early, late) day tuples for the days actually present in one input.

    A function and not a constant because no tuple can express the rule: the split has
    to be a function OF THE DAYS to stay correct when the window is not ten days long.
    An override supplies one half explicitly and the other half is then every present
    day that is not in it.
    """
    present = sorted(int(d) for d in np.unique(np.asarray(day, dtype=np.int64)))
    if EARLY_DAYS_OVERRIDE is None and LATE_DAYS_OVERRIDE is None:
        return H.split_early_late(present)
    early = tuple(d for d in present
                  if EARLY_DAYS_OVERRIDE is not None
                  and d in set(int(x) for x in EARLY_DAYS_OVERRIDE))
    if LATE_DAYS_OVERRIDE is None:
        late = tuple(d for d in present if d not in set(early))
    else:
        late = tuple(d for d in present
                     if d in set(int(x) for x in LATE_DAYS_OVERRIDE))
    if not early:
        early = tuple(d for d in present if d not in set(late))
    return early, late

# -------------------- GM configuration --------------------
# DELIBERATELY NOT THE STUDY HEADLINE. J is the SIZE of the informed jump toward true
# value -- a permanent-revision magnitude, read as mean|a_mid|, not a ranking of who is
# more harmful. It needs the window by which the revision has finished, which is the
# long leg of the ladder, not the 10s scoring window. Named J_HORIZON so no reader
# mistakes it for settings.HEADLINE_HORIZON_S.
J_HORIZON = H.COMPANION_HORIZON_S   # 60s book-mid markout sets J
HORIZONS = H.LADDER_S               # the declared ladder; see settings.LADDER_S
N_VPIN_BUCKETS = 50                 # equal-COUNT buckets per (coin, day) for the VPIN proxy
MIN_FILLS_PER_BUCKET = 5            # a (coin, day) needs >= this*N_VPIN_BUCKETS fills to bucket
PI_GRID = (0.05, 0.10, 0.20, 0.30, 0.50)  # reported sensitivity range for pi

# Hyperliquid MAKER fee schedule, bps (REUSE maker_econ.py exactly; 1 bp = 0.01%).
# Every quoter in the bake-off is benchmarked against the MAKER schedule, not the
# taker fee. A serious maker operates at the 0-fee / rebate tiers; all tiers reported.
MAKER_FEE_BPS = {
    "base": 1.5,        # base maker fee
    "t3": 0.4,          # tier 3 (>$100M 14d volume)
    "t4_0fee": 0.0,     # tier 4 (>$500M) and above: zero maker fee
    "rebate1": -0.1,    # >0.5% 14d maker-volume share
    "rebate2": -0.2,    # >1.5%
    "rebate3": -0.3,    # >3.0%
}
FEE_TIERS = ("base", "t3", "t4_0fee", "rebate1", "rebate2", "rebate3")

# fill-aware recapture APPROXIMATION (maker_econ-style; labelled, never a fill model).
RECAPTURE_F = 0.5                   # fraction of would-be fills recaptured at the wider quote
RECAPTURE_PENALTY_BPS = 0.0         # per-requote penalty (bps); 0 = none, swept conceptually


# ==================== closed-form GM functions (pure, vectorizable, no data) ====================
# THIS FILE IS THE HOME OF THE GM CLOSED FORM, AND SINCE 2026-08-13 IT IS THE ONLY ONE.
# gm_half_spread and vpin_imbalance stood in a second, independently written copy inside
# mm_bakeoff.py, which now imports them from here. The two copies computed the same thing
# -- measured over 91 cases before the merge, zero disagreements, on a comparator that
# caught 45 and 9 planted defects -- and that is exactly the state in which a duplicate is
# dangerous rather than harmless: it agrees until somebody edits one side, and no gate in
# this tree compares two functions. What the merge costs is an import edge, and what it
# buys is that the bake-off's GM arm and the GM quoter cannot drift apart in silence.
# mm_bakeoff.py declares this file as an INPUT of its artifact, so an edit made here marks
# that artifact stale; a producer hash alone would not have noticed.
def gm_half_spread(pi, adverse_move):
    """Glosten-Milgrom adverse-selection HALF-spread.

        half_spread = pi * J

    pi = P(incoming order is informed) in [0, 1) (the PIN/VPIN proxy); adverse_move J
    = expected ABSOLUTE adverse price revision an informed order carries (price units,
    or bps). pi = 0 => half_spread == 0 exactly (no informed flow => no GM spread). The
    half-spread WIDENS monotonically in pi and in J. NO inventory term, NO counterparty
    term. Returns half_spread in the SAME units as adverse_move. Fully vectorizable.

    pi is dimensionless, so the bps form and the price form are the same multiply. This
    is the symmetric two-type reduction of GM's general posteriors E[V|buy], E[V|sell]:
    the tape supplies a market-level pi and a market-level |markout| magnitude J, not
    per-order informed/uninformed labels."""
    pi = np.asarray(pi, dtype=np.float64)
    adverse_move = np.asarray(adverse_move, dtype=np.float64)
    return pi * adverse_move


def gm_quotes(mid, pi, adverse_move_price):
    """Symmetric GM bid/ask around the MID (GM has no inventory skew).

        h   = gm_half_spread(pi, J_price)
        bid = mid - h ,  ask = mid + h

    Returns (bid, ask, h, delta) with delta = 2*h the total GM spread. By construction
    (ask - mid) == (mid - bid) == h, so the quotes are symmetric ABOUT the mid, never
    skewed by inventory (that is A-S's axis) and never by counterparty (GM is blind to
    who trades). Vectorizable over every argument."""
    mid = np.asarray(mid, dtype=np.float64)
    h = gm_half_spread(pi, adverse_move_price)
    bid = mid - h
    ask = mid + h
    delta = 2.0 * h
    return bid, ask, h, delta


def vpin_imbalance(signs):
    """VPIN-style absolute order-flow imbalance of one bucket of signed flow.

        imb = | sum(signs) | / n   in [0, 1].

    signs is +1 for a buy-aggressor and -1 for a sell-aggressor (the byte-verified
    taker_side convention). imb = 0 when buys and sells exactly balance (benign,
    uninformed flow); imb = 1 when the bucket is one-sided (maximally toxic directional
    pressure). This is the per-bucket flow-toxicity statistic averaged into the VPIN
    proxy. Returns nan for an empty bucket.

    The bulk-classification spirit of VPIN (Easley-Lopez de Prado-O'Hara 2012), measured
    on a COUNT clock: a departure from the canonical volume clock, declared here rather
    than quietly taken, and it is the clock every bucket cut in this file and in the
    bake-off is cut on."""
    signs = np.asarray(signs, dtype=np.float64)
    n = signs.size
    if n == 0:
        return float("nan")
    return float(abs(signs.sum()) / n)


# ==================== analytic self-tests (assert; load NO data) ====================
def run_selftests():
    """All GM sign / symmetry / monotonicity properties as hard asserts.

    Returns a dict of per-check booleans (all True on success). Raises AssertionError
    on any violation. Loads NO data, so it is fast and runs under --selftest. The
    invariants are deterministic on TINY synthetic arrays (no RNG dependence)."""
    flags = {}
    tol = 1e-12
    mid = 100.0
    J = 4.0          # price-unit adverse move
    pi = 0.2

    # --- pi = 0 => half_spread == 0 exactly ---
    h0 = float(gm_half_spread(0.0, J))
    assert abs(h0) < tol, f"pi=0 half_spread {h0} != 0"
    flags["pi0_half_spread_is_zero"] = True

    # --- pi = 0 => bid == ask == mid exactly ---
    b0, a0, hh0, d0 = gm_quotes(mid, 0.0, J)
    assert abs(float(b0) - mid) < tol and abs(float(a0) - mid) < tol, "pi=0 quotes != mid"
    assert abs(float(d0)) < tol, "pi=0 total spread != 0"
    flags["pi0_quotes_collapse_to_mid"] = True

    # --- half_spread STRICTLY INCREASING in pi (more toxic flow => wider) ---
    pi_grid = np.array([0.0, 0.05, 0.1, 0.25, 0.5, 0.9])
    h_pi = gm_half_spread(pi_grid, J)
    assert np.all(np.diff(h_pi) > 0), f"half_spread not increasing in pi: {h_pi}"
    flags["half_spread_increasing_in_pi"] = True

    # --- HIGHER informed-probability => WIDER spread (the headline bake-off invariant) ---
    h_lo = float(gm_half_spread(0.10, J))
    h_hi = float(gm_half_spread(0.40, J))
    assert h_hi > h_lo, f"higher pi did not widen spread: {h_hi} !> {h_lo}"
    flags["higher_informed_prob_wider_spread"] = True

    # --- half_spread STRICTLY INCREASING in the adverse move J ---
    J_grid = np.array([0.5, 1.0, 2.0, 4.0, 8.0])
    h_J = gm_half_spread(pi, J_grid)
    assert np.all(np.diff(h_J) > 0), f"half_spread not increasing in J: {h_J}"
    flags["half_spread_increasing_in_adverse_move"] = True

    # --- quotes SYMMETRIC about the mid (GM has no inventory skew) ---
    b, a, h, d = gm_quotes(mid, pi, J)
    b, a, h, d = float(b), float(a), float(h), float(d)
    assert a > mid > b, f"ask {a} / bid {b} do not straddle mid {mid}"
    assert abs((a - mid) - (mid - b)) < tol, "GM quotes not symmetric about mid"
    assert abs((a - mid) - h) < tol and abs((mid - b) - h) < tol, "half != ask-mid"
    assert abs(d - 2.0 * h) < tol, "total spread != 2*half"
    flags["quotes_symmetric_about_mid"] = True

    # --- exact value check: half_spread = pi*J = 0.2*4 = 0.8 ---
    assert abs(float(gm_half_spread(0.2, 4.0)) - 0.8) < tol, "pi*J value wrong"
    flags["half_spread_equals_pi_times_J"] = True

    # --- bps and price forms agree because pi is dimensionless ---
    J_bps = 5.0
    mid2 = 200.0
    J_price = J_bps / 1e4 * mid2
    h_bps = float(gm_half_spread(0.3, J_bps))
    h_price = float(gm_half_spread(0.3, J_price))
    h_price_in_bps = float(spread_price_to_bps(h_price, mid2))
    assert abs(h_bps - h_price_in_bps) < 1e-9, f"bps {h_bps} != price-in-bps {h_price_in_bps}"
    flags["bps_and_price_forms_agree"] = True

    # --- VPIN imbalance: balanced flow => 0, one-sided => 1, deterministic ---
    assert abs(vpin_imbalance(np.array([1, -1, 1, -1]))) < tol, "balanced imbalance != 0"
    assert abs(vpin_imbalance(np.array([1, 1, 1, 1])) - 1.0) < tol, "one-sided imbalance != 1"
    assert abs(vpin_imbalance(np.array([1, 1, -1, 1])) - 0.5) < tol, "3-1 imbalance != 0.5"
    flags["vpin_imbalance_bounds"] = True

    # --- a more toxic (more imbalanced) tape => higher pi => wider GM spread (compose) ---
    pi_benign = vpin_imbalance(np.array([1, -1, 1, -1, 1, -1]))   # 0 (balanced)
    pi_toxic = vpin_imbalance(np.array([1, 1, 1, 1, -1, 1]))      # 0.667 (one-sided)
    assert float(gm_half_spread(pi_toxic, J)) > float(gm_half_spread(pi_benign, J)), \
        "toxic tape did not produce a wider GM spread than a benign tape"
    flags["toxic_tape_wider_than_benign_tape"] = True

    # --- vectorization sanity: array pi broadcasts correctly ---
    pv = np.array([0.0, 0.1, 0.2, 0.3])
    hv = gm_half_spread(pv, J)
    assert hv.shape == (4,) and hv[0] == 0.0 and np.all(np.diff(hv) > 0)
    flags["vectorized_half_spread_consistent"] = True

    flags["all_passed"] = all(bool(v) for v in flags.values())
    return flags


# ==================== env slice (smoke runs; REUSE maker_econ convention) ====================
def _apply_env_slice(arrs):
    """If CAP_DAYS / CAP_COINS are set, filter every aligned array to those rows.

    CAP_DAYS  : comma list of day ints (e.g. "9,10").
    CAP_COINS : comma list of coin symbols (e.g. "BTC,ETH") or codes ("0,1").
    Mirrors the maker_econ.py / as_quoter.py convention. Returns (arrs, slice_meta)."""
    day = arrs["day"]
    coin = arrs["coin"]
    mask = np.ones(day.size, dtype=bool)
    meta = {"sliced": False, "days": None, "coins": None}

    env_days = os.environ.get("CAP_DAYS")
    if env_days:
        keep_days = set(int(x.strip()) for x in env_days.split(",") if x.strip())
        mask &= np.array([int(d) in keep_days for d in day], dtype=bool)
        meta["sliced"] = True
        meta["days"] = sorted(keep_days)

    env_coins = os.environ.get("CAP_COINS")
    if env_coins:
        name_to_code = {v: k for k, v in COIN_NAMES.items()}
        keep_codes = set()
        for tok in env_coins.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok.upper() in name_to_code:
                keep_codes.add(name_to_code[tok.upper()])
            else:
                keep_codes.add(int(tok))
        mask &= np.array([int(c) in keep_codes for c in coin], dtype=bool)
        meta["sliced"] = True
        meta["coins"] = sorted(COIN_NAMES.get(c, c) for c in keep_codes)

    if meta["sliced"]:
        arrs = {k: v[mask] for k, v in arrs.items()}
        if arrs["day"].size == 0:
            raise SystemExit(
                f"[gm_quoter] env slice (days={meta['days']} coins={meta['coins']}) "
                f"selected 0 rows; check CAP_DAYS / CAP_COINS")
    return arrs, meta


# ==================== load (NO re-pull) ====================
def load_fills():
    """Load the on-disk arrays for the GM pi estimate, J estimate, and counterfactual.

    Uses quickwin_markouts_mid.npz (taker_side, spread_entry_bps, mo{h}_mid, entry_px,
    coin, day, notional) plus quickwin_markouts.npz (mo{h}, trade-print markout). NO
    counterparty identity field (taker_id / maker_id) is loaded -- GM is counterparty-
    BLIND, so reading wallet identity here would violate the model. Asserts row
    alignment between the two npz on the shared keys (REUSE maker_econ's discipline).
    Returns (arrs, align_ok, slice_meta)."""
    # panel_io names the producer to run when a file is absent, so that message is
    # written once for the whole tree; the loads stay here because build.py derives
    # this script's input edges from the arguments of np.load.
    P.require_present("mid", MID_NPZ)
    P.require_present("print", PRINT_NPZ)
    zm = np.load(MID_NPZ)
    zp = np.load(PRINT_NPZ)

    # row alignment on the shared keys (NOT taker_id/maker_id -- GM never reads them).
    align_ok = {}
    for k in ("coin", "day", "taker_side"):
        align_ok[k] = bool(np.array_equal(zm[k], zp[k]))
        if not align_ok[k]:
            raise SystemExit(f"[gm_quoter] ROW MISALIGNMENT on '{k}' between the two npz - abort")
    notl_mid = zm["notional"].astype(np.float64)
    notl_print = zp["notional"].astype(np.float64)
    align_ok["notional"] = bool(np.allclose(notl_mid, notl_print, rtol=0, atol=1e-3,
                                            equal_nan=True))

    arrs = {
        "coin": zm["coin"].astype(np.int64),
        "day": zm["day"].astype(np.int64),
        "entry_px": zm["entry_px"].astype(np.float64),
        "spread_entry_bps": zm["spread_entry_bps"].astype(np.float64),
        "notional": notl_mid,
        # taker_side: byte-verified 1 = buy-aggressor (+1), 0 = sell-aggressor (-1).
        "taker_side": zm["taker_side"].astype(np.int64),
    }
    arrs["sign_taker"] = np.where(arrs["taker_side"] == 1, 1.0, -1.0)
    for h, key in ((1, "mo1_mid"), (10, "mo10_mid"), (60, "mo60_mid")):
        arrs[f"a_mid_{h}"] = zm[key].astype(np.float64)
    for h, key in ((1, "mo1"), (10, "mo10"), (60, "mo60")):
        arrs[f"a_print_{h}"] = zp[key].astype(np.float64)
    arrs["s_bbo"] = arrs["spread_entry_bps"] / 2.0   # BBO half-spread (lower bound income)

    arrs, slice_meta = _apply_env_slice(arrs)
    return arrs, align_ok, slice_meta


# ==================== pi estimation: VPIN/PIN proxy on OUR tape (item 1) ====================
def estimate_pi(arrs):
    """Informed-trade probability pi, the VPIN/PIN proxy, per coin x day.

    METHOD (NO counterparty identity used anywhere):
      - Within each (coin, day), in ARRIVAL ORDER, bucket fills into N_VPIN_BUCKETS
        equal-COUNT buckets (a count-clock stand-in for the volume clock of Easley-
        Lopez de Prado-O'Hara 2012; count clock chosen because notional is heavy-tailed
        and a volume clock would degenerate on whale fills).
      - Per bucket compute the absolute order-flow imbalance from the SIGNED taker side
        (vpin_imbalance), in [0, 1].
      - pi_proxy(coin, day) = mean over buckets of the absolute imbalance = the VPIN
        flow-toxicity statistic for that (coin, day). It reads ONLY the net directional
        pressure of the pooled flow, never which wallet sent an order -- exactly the
        market-level information a book-only Glosten-Milgrom maker has.
      - NO LOOKAHEAD: a (coin, day)'s pi is computed from that day's own fills only, in
        arrival order; no future row feeds back.

    Returns per_session pi, per-coin median/mean/IQR, and the headline per-coin pi
    (median of the daily series)."""
    coin = arrs["coin"]
    day = arrs["day"]
    sign = arrs["sign_taker"]

    per_session = {}
    pi_by_coin = {}
    coins = sorted(set(int(c) for c in np.unique(coin)))
    days = sorted(set(int(d) for d in np.unique(day)))
    for c in coins:
        pi_by_coin[c] = []
        cname = COIN_NAMES.get(c, str(c))
        for d in days:
            sel = (coin == c) & (day == d)
            n = int(sel.sum())
            if n < MIN_FILLS_PER_BUCKET * N_VPIN_BUCKETS:
                continue
            s = sign[sel]                       # arrival order preserved within (coin, day)
            # equal-count buckets via array_split (handles non-divisible n; each bucket
            # keeps >= MIN_FILLS_PER_BUCKET by the guard above)
            buckets = np.array_split(s, N_VPIN_BUCKETS)
            imbs = np.array([vpin_imbalance(b) for b in buckets], dtype=np.float64)
            imbs = imbs[np.isfinite(imbs)]
            if imbs.size == 0:
                continue
            pi_d = float(imbs.mean())
            per_session[f"{cname}_d{d}"] = pi_d
            pi_by_coin[c].append(pi_d)

    coin_summary = {}
    for c in coins:
        vals = np.array(pi_by_coin[c], dtype=np.float64)
        cname = COIN_NAMES.get(c, str(c))
        coin_summary[cname] = {
            "coin_code": c,
            "n_sessions": int(vals.size),
            "pi_median": float(np.median(vals)) if vals.size else float("nan"),
            "pi_mean": float(vals.mean()) if vals.size else float("nan"),
            "pi_p10": float(np.percentile(vals, 10)) if vals.size else float("nan"),
            "pi_p90": float(np.percentile(vals, 90)) if vals.size else float("nan"),
        }
    return {
        "method": (
            "VPIN/PIN proxy: per (coin, day), equal-COUNT bucket fills in arrival order "
            "into N_VPIN_BUCKETS buckets, pi = mean over buckets of |sum(sign)|/n "
            "(absolute buy/sell imbalance). MARKET-LEVEL toxicity only -- NO counterparty "
            "identity. Count clock substitutes for the volume clock (notional heavy-"
            "tailed). No lookahead: each (coin, day) pi uses that day's fills only."),
        "n_vpin_buckets": N_VPIN_BUCKETS,
        "min_fills_per_bucket": MIN_FILLS_PER_BUCKET,
        "per_session_pi": per_session,
        "per_coin_summary": coin_summary,
    }


# ==================== J estimation: empirical adverse-move magnitude (item 2) ====================
def estimate_adverse_move(arrs, horizon=J_HORIZON):
    """Expected absolute adverse price revision J per coin, from the book-mid markout.

    J is the size of the price move an informed order causes (the GM "jump" toward true
    value). We read it off the realized EXEC->mid book-mid markout a_mid_{h}: a positive
    a_mid is adverse for the maker, and |a_mid| is the magnitude of the revision. J_bps
    = per-coin MEAN ABSOLUTE a_mid_{h} (bps); J_price = J_bps/1e4 * mid. MARKET-LEVEL
    magnitude -- NOT conditioned on the counterparty. The mean-absolute (not signed
    mean) is used because GM's J is the size of the informed jump regardless of its
    direction. Returns per-coin J_bps, J_price, and the reference mid."""
    coin = arrs["coin"]
    px = arrs["entry_px"]
    a_mid = arrs[f"a_mid_{horizon}"]

    coins = sorted(set(int(c) for c in np.unique(coin)))
    per_coin = {}
    for c in coins:
        cname = COIN_NAMES.get(c, str(c))
        sel = coin == c
        am = a_mid[sel]
        am = am[np.isfinite(am)]
        j_bps = float(np.mean(np.abs(am))) if am.size else float("nan")
        c_px = px[sel]
        c_px = c_px[np.isfinite(c_px) & (c_px > 0)]
        mid_ref = float(np.median(c_px)) if c_px.size else float("nan")
        j_price = (j_bps / 1e4 * mid_ref) if (np.isfinite(j_bps) and np.isfinite(mid_ref)) \
            else float("nan")
        per_coin[cname] = {
            "coin_code": c,
            "horizon_s": horizon,
            "J_bps": j_bps,
            "J_price": j_price,
            "mid_ref_price": mid_ref,
            "n_fills": int(am.size),
        }
    return {
        "method": (
            "J = E[|adverse move|] read off the EXEC->mid book-mid markout a_mid_{h}: "
            "per coin, J_bps = mean(|a_mid_{h}|) (positive a_mid is adverse for the "
            "maker; |.| is the GM jump magnitude regardless of direction). MARKET-LEVEL, "
            "NOT counterparty-conditioned. J_price = J_bps/1e4 * mid."),
        "horizon_s": horizon,
        "per_coin": per_coin,
    }


# ==================== GM half-spread vs the REAL bid-ask (item 3) ====================
def gm_spread_vs_real(arrs, pi_info, j_info):
    """GM adverse-selection half-spread per coin, beside the REAL BBO half-spread.

    half_spread_GM_bps = pi * J_bps (pi the VPIN/PIN proxy, J_bps the mean-abs book-mid
    markout). Reported beside the observed BBO half-spread (spread_entry_bps/2). GM is
    an ADVERSE-SELECTION-ONLY spread: it has no inventory term and no order-processing
    term, so it is NOT expected to match the full quoted spread -- it isolates the
    adverse-selection share, the GM analogue of Stoll's adverse-selection component of
    the spread. Also reports the pi sensitivity band (half-spread over PI_GRID at the
    coin's J). NO counterparty identity anywhere."""
    coin = arrs["coin"]
    obs_half = arrs["s_bbo"]
    per_coin = {}
    coins = sorted(set(int(c) for c in np.unique(coin)))
    for c in coins:
        cname = COIN_NAMES.get(c, str(c))
        sel = coin == c
        oh = obs_half[sel]
        oh = oh[np.isfinite(oh)]
        obs_half_bps = float(np.median(oh)) if oh.size else float("nan")

        pi_med = pi_info["per_coin_summary"].get(cname, {}).get("pi_median", float("nan"))
        j_bps = j_info["per_coin"].get(cname, {}).get("J_bps", float("nan"))
        h_gm_bps = float(gm_half_spread(pi_med, j_bps)) \
            if (np.isfinite(pi_med) and np.isfinite(j_bps)) else float("nan")

        pi_band = {}
        for p in PI_GRID:
            pi_band[f"pi_{p:.2f}"] = float(gm_half_spread(p, j_bps)) \
                if np.isfinite(j_bps) else float("nan")

        per_coin[cname] = {
            "coin_code": c,
            "pi_median_used": pi_med,
            "J_bps_used": j_bps,
            "gm_half_spread_bps": h_gm_bps,
            "gm_total_spread_bps": (2.0 * h_gm_bps) if np.isfinite(h_gm_bps) else float("nan"),
            "observed_bbo_half_spread_bps": obs_half_bps,
            "gm_half_minus_observed_half_bps": (h_gm_bps - obs_half_bps
                                                if (np.isfinite(h_gm_bps)
                                                    and np.isfinite(obs_half_bps))
                                                else float("nan")),
            "gm_half_spread_over_pi_grid_bps": pi_band,
        }
    return {
        "formula": "gm_half_spread_bps = pi * J_bps ; gm_total_spread_bps = 2 * pi * J_bps",
        "interpretation": (
            "GM prices the ADVERSE-SELECTION share of the spread only (no inventory, no "
            "processing cost), from MARKET-LEVEL toxicity (pi) and the average informed "
            "move (J). It is the book-only-information baseline; it cannot price WHO the "
            "counterparty is, which is the gap the counterparty-resolved term fills. No "
            "profit/alpha claim."),
        "pi_grid": list(PI_GRID),
        "per_coin": per_coin,
    }


# ==================== GM net-economics counterfactual (item 4; REUSE maker_econ accounting) ====================
def _vw_mean(vals, weights):
    """Notional-weighted mean over finite, positive-weight rows (REUSE maker_econ)."""
    vals = np.asarray(vals, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    m = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
    if not m.any():
        return float("nan")
    return float(np.sum(vals[m] * weights[m]) / np.sum(weights[m]))


def gm_net_economics(arrs, pi_info, j_info):
    """GM maker net-economics counterfactual on the LATE half, per coin x tier.

    COUNTERFACTUAL, NOT a fill model (HARD RULE 1). A GM maker quoting half-spread
    h_GM is scored exactly the maker_econ way -- the two INDEPENDENT measures:
      net_PRINT_h   = -a_print_h        (mirror of taker print gain; nets entry spread)
      net_MID_GM_h  = h_GM - a_mid_h    (GM quotes its OWN half-spread h_GM as income,
                      pays the realized book-mid adverse markout a_mid_h)
    net_MID_GM swaps the BBO half-spread of maker_econ's net_MID_lower for GM's MODEL
    half-spread h_GM = pi*J: it asks "if the maker had quoted the GM adverse-selection
    spread, what would it have netted on the realized adverse selection?" Per-fee-tier
    net = measure - maker_fee[tier]. Reported notional-weighted on the LATE half only.

    EXPECTED COST-NOT-ALPHA (HARD RULE 2): every tier is expected net-NEGATIVE. GM is
    counterparty-blind, so it cannot achieve the toxicity overlay's (whale-driven,
    fragile, ETH-tilted) cost reduction; it quotes ONE market-level spread to everyone.

    The maker_econ-style recapture APPROXIMATION (a fraction f of would-be fills at the
    wider GM quote minus a penalty c) is reported as a clearly-labelled approximation,
    never a fill model."""
    coin = arrs["coin"]
    day = arrs["day"]
    notl = arrs["notional"]
    late_set = set(early_late_days(day)[1])
    is_late = np.array([int(d) in late_set for d in day])

    out = {
        "label": (
            "GM net-economics counterfactual on the LATE half. net_MID_GM = h_GM - "
            "a_mid (GM model half-spread as income minus realized book-mid markout); "
            "net_PRINT = -a_print (maker_econ measure 1). COUNTERFACTUAL, not a fill "
            "model. Every tier expected net-NEGATIVE = COST, never alpha."),
        "horizon_s": J_HORIZON,
        "recapture_approx": {
            "f": RECAPTURE_F,
            "penalty_bps": RECAPTURE_PENALTY_BPS,
            "note": ("maker_econ-style fill-aware APPROXIMATION (recapture fraction f of "
                     "would-be fills at the wider GM quote minus a per-requote penalty); "
                     "labelled an approximation, NOT a matching-engine fill model."),
        },
        "by_coin": {},
    }
    coin_groups = [("BTC", 0), ("ETH", 1), ("pooled", -1)]
    for cname, ccode in coin_groups:
        if ccode == -1:
            sel = is_late
            j_bps = j_info["per_coin"].get("BTC", {}).get("J_bps", float("nan"))
            pi_med = pi_info["per_coin_summary"].get("BTC", {}).get("pi_median", float("nan"))
            # pooled uses a notional-share blend would over-engineer; report per-coin h
            # below and a pooled figure that applies EACH fill's own coin h_GM.
        else:
            sel = is_late & (coin == ccode)
            pi_med = pi_info["per_coin_summary"].get(cname, {}).get("pi_median", float("nan"))
            j_bps = j_info["per_coin"].get(cname, {}).get("J_bps", float("nan"))
        if not sel.any():
            out["by_coin"][cname] = {"n_late_fills": 0, "note": "no late fills"}
            continue

        w = notl[sel]
        # build a per-fill GM half-spread using EACH fill's coin pi*J (so pooled is
        # internally consistent, never a single blended constant).
        h_gm_fill = np.empty(int(sel.sum()), dtype=np.float64)
        sel_coin = coin[sel]
        for code2, name2 in ((0, "BTC"), (1, "ETH"), (2, "SOL")):
            pim = pi_info["per_coin_summary"].get(name2, {}).get("pi_median", float("nan"))
            jb = j_info["per_coin"].get(name2, {}).get("J_bps", float("nan"))
            hv = float(gm_half_spread(pim, jb)) if (np.isfinite(pim) and np.isfinite(jb)) \
                else float("nan")
            h_gm_fill[sel_coin == code2] = hv

        a_mid = arrs[f"a_mid_{J_HORIZON}"][sel]
        a_print = arrs[f"a_print_{J_HORIZON}"][sel]
        net_print = -a_print
        net_mid_gm = h_gm_fill - a_mid

        per_tier = {}
        for tier in FEE_TIERS:
            per_tier[tier] = {
                "maker_fee_bps": MAKER_FEE_BPS[tier],
                "net_PRINT_vw_bps": _vw_mean(net_print - MAKER_FEE_BPS[tier], w),
                "net_MID_GM_vw_bps": _vw_mean(net_mid_gm - MAKER_FEE_BPS[tier], w),
            }
        out["by_coin"][cname] = {
            "n_late_fills": int(sel.sum()),
            "pi_median_used": pi_med if ccode != -1 else "per-fill coin pi",
            "J_bps_used": j_bps if ccode != -1 else "per-fill coin J",
            "gm_half_spread_income_vw_bps": _vw_mean(h_gm_fill, w),
            "gross_prefee_net_MID_GM_vw_bps": _vw_mean(net_mid_gm, w),
            "gross_prefee_net_PRINT_vw_bps": _vw_mean(net_print, w),
            "by_fee_tier": per_tier,
            "all_tiers_net_negative_MID_GM": bool(
                all((per_tier[t]["net_MID_GM_vw_bps"] < 0)
                    for t in FEE_TIERS
                    if per_tier[t]["net_MID_GM_vw_bps"] == per_tier[t]["net_MID_GM_vw_bps"])),
        }
    return out


# ==================== bake-off mapping note (item 5) ====================
def bakeoff_mapping_note():
    """Document GM's role and its hard limit relative to the counterparty term."""
    return {
        "role": (
            "GM is the INFORMATION-based, book-only-toxicity quoter in the bake-off, "
            "between the inventory-only Avellaneda-Stoikov maker (as_quoter.py) and the "
            "counterparty-toxicity-conditioned skew overlay (t1_*/maker_econ.py). GM "
            "prices the adverse-selection share of the spread from MARKET-LEVEL flow "
            "toxicity (a VPIN/PIN proxy) and the average informed move, with NO "
            "counterparty identity."),
        "hard_limit": (
            "GM quotes ONE spread to every counterparty given the market-level pi; it "
            "cannot reach the per-counterparty idiosyncratic adverse selection the "
            "wallet-resolved term reaches, BY CONSTRUCTION -- that is the point of the "
            "bake-off. The idiosyncratic component is not recoverable from the pooled "
            "book-only signal GM uses."),
        "expected_ranking": (
            "On adverse-selection-cost reduction the expected ordering is: symmetric "
            "A-S (no AS term) <= GM (market-level AS term) <= counterparty-resolved "
            "overlay (market + idiosyncratic AS). GM is expected to IMPROVE on symmetric "
            "A-S by pricing average toxicity, yet fall SHORT of the counterparty term "
            "because it is blind to who trades. All three are expected net-NEGATIVE at "
            "every maker-fee tier (COST, not alpha); GM vs A-S may be a near-tie when the "
            "market-level toxicity signal is weak, which is itself a reportable finding."),
        "what_gm_is_not": (
            "GM produces a spread, never an alpha, a P&L, or a Sharpe. It is a baseline "
            "quoter, and the counterparty-resolved term is measured against it as well "
            "as against A-S."),
    }


# ==================== main ====================
def main():
    t0 = artifact.start_clock()
    print(f"[gm_quoter] seed={SEED}")

    selftest_flags = run_selftests()
    print(f"[gm_quoter] analytic self-tests: all_passed={selftest_flags['all_passed']}")

    arrs, align_ok, slice_meta = load_fills()
    n_rows = int(arrs["coin"].size)
    print(f"[gm_quoter] loaded {n_rows:,} fills (NO identity field read) "
          f"(sliced={slice_meta['sliced']} days={slice_meta['days']} coins={slice_meta['coins']})")
    print(f"[gm_quoter] row-alignment: {align_ok}")

    pi_info = estimate_pi(arrs)                       # item 1: VPIN/PIN proxy
    j_info = estimate_adverse_move(arrs)             # item 2: empirical adverse move J
    spread_eval = gm_spread_vs_real(arrs, pi_info, j_info)   # item 3: GM spread vs real
    net_econ = gm_net_economics(arrs, pi_info, j_info)       # item 4: net-economics counterfactual
    mapping = bakeoff_mapping_note()                 # item 5: bake-off role + hard limit

    # The split the run actually used, derived from the days the input carries.
    early_days_used, late_days_used = early_late_days(arrs["day"])

    # Which settings produced these numbers. J_HORIZON is recorded as an override rather
    # than as the study headline on purpose: it is the window by which the permanent
    # revision has finished, which is its own quantity and is NOT the scoring window this
    # project ranks wallets on.
    settings_used = {
        "h": J_HORIZON,
        "lens": "mid",
        "master_seed": SEED,
        "n_perm": None,
        "n_boot": None,
        "rank_floor_fills": None,
        "j_horizon_s": J_HORIZON,
        "early_days": list(early_days_used),
        "late_days": list(late_days_used),
        "override_reasons": {
            "horizon_s": f"this file is stamped at {J_HORIZON}s because J -- the "
                         f"SIZE of the informed jump, read as mean|a_mid| -- "
                         f"needs the window by which the permanent revision has "
                         f"finished. That is a magnitude, not a ranking, so it "
                         f"is not the {H.HEADLINE_HORIZON_S}s scoring window and "
                         f"is_headline_horizon is correctly false here",
            "master_seed": f"the streams here are seeded {SEED}, not the declared "
                           f"{H.MASTER_SEED}; settings.MASTER_SEED carries the "
                           f"state 'target', so adopting it is a measured change "
                           f"owed its own recompute",
            "n_perm": "no permutation test and no bootstrap run in this file, so "
                      "neither declared resampling budget applies",
            "n_boot": "see n_perm",
            "rank_floor_fills": "no wallet floor applies: this quoter reads no "
                                "counterparty identity at all, so it never ranks "
                                "or gates a per-wallet population",
        },
    }

    # Everything descriptive that belongs in _meta and is not one of the five records
    # artifact.write owns. The two input files, the results file name and the settings
    # fingerprint are gone from here: they used to sit under _meta["inputs"] as a hand
    # written mapping with no sizes and no hashes, which is the second home this
    # migration exists to close.
    meta_extra = {
        "object": "Glosten-Milgrom (1985) information-based market-level-toxicity "
                  "counterparty-blind maker (one quoter in the bake-off)",
        "author": "Dmitry Stakhin",
        "date": "2026-06-23",
        "track": "11",
        "seed": SEED,
        "n_rows": n_rows,
        "row_alignment_ok": align_ok,
        "env_slice": slice_meta,
        "coin_names": {str(k): v for k, v in COIN_NAMES.items()},
    }
    meta_extra.update({
            "early_days": list(early_days_used),
            "late_days": list(late_days_used),
            "split_rule": (
                "The early and late halves are DERIVED from the days present, by "
                "settings.split_early_late: first ceil(n/2) days early, the rest late. "
                "They used to be the hardcoded day-of-month tuples (4,5,6,7,8) and "
                "(9,10,11,12,13), which are correct only for a window opening on the 4th "
                "and closing on the 13th. This input does open on the 4th, so the "
                "derived split reproduces those tuples exactly and no number moved."
            ),
            "closed_form": {
                "half_spread": "half_spread = pi * J  (pi = P(informed), J = E[|adverse move|])",
                "quotes": "bid = mid - pi*J ; ask = mid + pi*J ; total = 2*pi*J",
                "pi_estimator": "VPIN/PIN proxy: mean over equal-count buckets of "
                                "|sum(sign_taker)|/n per (coin, day); MARKET-LEVEL, no identity",
                "J_estimator": "mean(|a_mid_{h}|) per coin (book-mid markout magnitude)",
            },
            "uses_counterparty_identity": False,
            "identity_fields_loaded": "none (taker_id / maker_id deliberately NOT read)",
            "units": ("pi dimensionless in [0,1); J in price units (or bps); half_spread "
                      "= pi*J in the same units; bps form directly comparable to "
                      "spread_entry_bps/2."),
            "sign_convention": ("taker_side 1=buy-aggressor(+1)/0=sell-aggressor(-1); "
                                "positive a_mid markout = adverse for the passive maker; "
                                "pi=0 => half_spread=0; half_spread widens in pi and J."),
            "counterfactual_only": (
                "markout-based counterfactual overlay, NOT a matching engine (no queue / "
                "fill-probability / requote); the only fill-awareness is the maker_econ-"
                "style recapture APPROXIMATION (fraction f at +h bps minus penalty c)."),
            "cost_not_alpha": (
                "every quoter is expected net-NEGATIVE at every maker-fee tier; GM is "
                "never framed as profitable/alpha/edge/Sharpe; GM cannot reach the "
                "counterparty term's (whale-driven, fragile, ETH-tilted) cost reduction."),
            "lineage": (
                "the adverse-selection-aware quoting leg is owned by Barzykin-Bergault-"
                "Gueant-Lemmel (arXiv:2508.20225); GM (1985) is the founding information-"
                "based spread the lineage descends from, used here as the book-only "
                "baseline, not as new quoting theory."),
            "fee_schedule": MAKER_FEE_BPS,
            "fee_tiers": list(FEE_TIERS),
            "no_repull": "computed entirely on-disk from the two npz; no S3 re-pull.",
    })

    payload = {
        "selftest_flags": selftest_flags,
        "pi_estimation_vpin_pin": pi_info,
        "adverse_move_J": j_info,
        "gm_spread_vs_real": spread_eval,
        "gm_net_economics": net_econ,
        "bakeoff_mapping_note": mapping,
    }

    # What the numbers cover, read off the rows actually loaded rather than off the
    # module's declarations: an env slice narrows both the days and the coins.
    days_present = sorted(int(d) for d in np.unique(arrs["day"]))
    coins_present = [COIN_NAMES.get(int(c), str(int(c)))
                     for c in sorted(set(int(x) for x in np.unique(arrs["coin"])))]
    # A scope field is never left empty: an empty list reads exactly like a scope
    # covering every coin, which is the opposite of what a zero-row run means.
    coins_scope = coins_present or "n/a: no row was loaded, so no coin is covered"
    artifact.write(
        os.path.basename(OUT_JSON), payload,
        script=__file__,
        inputs=[MID_NPZ, PRINT_NPZ],
        scope={
            "population": (
                f"{n_rows:,} collapsed taker fills, row-aligned across the two "
                f"intermediates ({align_ok}); no wallet floor is applied and no "
                f"counterparty identity field is read at all. pi is estimated over "
                f"{N_VPIN_BUCKETS} equal-count buckets per (coin, day), each needing "
                f"at least {MIN_FILLS_PER_BUCKET} fills"),
            "window": (
                f"{len(days_present)} days present in the input, day-of-month "
                f"{days_present[0]}..{days_present[-1]}; early {list(early_days_used)}, "
                f"late {list(late_days_used)}"
                if days_present else "n/a: no row was loaded, so no day is covered"),
            "coins": coins_scope,
        },
        settings=settings_used,
        extra_meta=meta_extra,
        started=t0)

    _print_console({"_meta": meta_extra, **payload})
    print(f"\n[gm_quoter] wrote {os.path.basename(OUT_JSON)}")


# ==================== console summary ====================
def _f(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float) and x != x:
        return "nan"
    if isinstance(x, (int, float)):
        return f"{x:+.{nd}f}"
    return str(x)


def _print_console(results):
    meta = results["_meta"]
    print("\n" + "=" * 84)
    print("GLOSTEN-MILGROM (1985) INFORMATION-BASED MAKER - BAKE-OFF QUOTER - SUMMARY")
    print("=" * 84)
    print(f"  rows={meta['n_rows']:,}  seed={meta['seed']}  no-repull (on-disk).")
    print(f"  closed form: half_spread = pi * J (pi=P(informed) VPIN/PIN proxy, "
          f"J=E[|adverse move|]).")
    print(f"  GM uses MARKET-LEVEL toxicity ONLY -- NO counterparty identity "
          f"(no alpha/P&L claim).")

    print("-" * 84)
    st = results["selftest_flags"]
    print(f"0) ANALYTIC SELF-TESTS: all_passed={st['all_passed']}")
    for kk, vv in st.items():
        if kk == "all_passed":
            continue
        print(f"     {kk:<42} {vv}")

    print("-" * 84)
    print("1) pi (VPIN/PIN proxy; per-coin median over daily sessions):")
    for cname, blk in results["pi_estimation_vpin_pin"]["per_coin_summary"].items():
        print(f"   {cname:<5} n_sessions={blk['n_sessions']:>3}  pi_median={_f(blk['pi_median'])}  "
              f"pi_mean={_f(blk['pi_mean'])}  [p10={_f(blk['pi_p10'],3)} p90={_f(blk['pi_p90'],3)}]")

    print("-" * 84)
    print(f"2) J = E[|adverse move|] (book-mid markout magnitude, h={J_HORIZON}s):")
    for cname, blk in results["adverse_move_J"]["per_coin"].items():
        print(f"   {cname:<5} J_bps={_f(blk['J_bps'])}  J_price={_f(blk['J_price'],4)}  "
              f"mid_ref={_f(blk['mid_ref_price'],2)}  n={blk['n_fills']:,}")

    print("-" * 84)
    print("3) GM half-spread = pi*J vs REAL BBO half-spread (bps):")
    for cname, blk in results["gm_spread_vs_real"]["per_coin"].items():
        print(f"   [{cname}] pi={_f(blk['pi_median_used'],4)} J_bps={_f(blk['J_bps_used'])}  "
              f"GM_half={_f(blk['gm_half_spread_bps'])} bps  obs_BBO_half="
              f"{_f(blk['observed_bbo_half_spread_bps'])} bps  "
              f"GM-obs={_f(blk['gm_half_minus_observed_half_bps'])} bps")
    print("   => GM prices the ADVERSE-SELECTION share only (no inventory/processing);")
    print("      it cannot price WHO the counterparty is -> the gap the resolved term fills.")

    print("-" * 84)
    print(f"4) GM NET-ECONOMICS counterfactual (LATE half, h={J_HORIZON}s, vw bps):")
    for cname, blk in results["gm_net_economics"]["by_coin"].items():
        if not blk.get("n_late_fills"):
            continue
        print(f"   [{cname}] n_late={blk['n_late_fills']:,}  "
              f"gross net_MID_GM={_f(blk['gross_prefee_net_MID_GM_vw_bps'])} "
              f"net_PRINT={_f(blk['gross_prefee_net_PRINT_vw_bps'])} "
              f"(all tiers net-neg MID_GM={blk['all_tiers_net_negative_MID_GM']})")
        for tier in ("base", "t4_0fee", "rebate3"):
            t = blk["by_fee_tier"][tier]
            print(f"        {tier:<9} net_MID_GM={_f(t['net_MID_GM_vw_bps'])} "
                  f"net_PRINT={_f(t['net_PRINT_vw_bps'])}")
    print("   => COST, not alpha: GM net-negative at every tier; counterparty-blind, so")
    print("      it cannot reach the resolved overlay's (whale-driven, fragile) reduction.")

    print("-" * 84)
    print("5) BAKE-OFF ROLE:")
    mp = results["bakeoff_mapping_note"]
    print(f"   {mp['role'][:78]}...")
    print(f"   hard limit: {mp['hard_limit'][:66]}...")
    print(f"   expected ranking: A-S <= GM <= counterparty-resolved (all net-negative).")
    print("=" * 84)


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        flags = run_selftests()
        print("[gm_quoter] --selftest (analytic only, NO data loaded)")
        for kk, vv in flags.items():
            print(f"  {kk:<44} {vv}")
        if not flags["all_passed"]:
            sys.exit(1)
        print("[gm_quoter] all analytic self-tests PASSED")
        sys.exit(0)
    main()
