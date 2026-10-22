#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: none (repository hygiene gate).

NO ABSOLUTE PATHS ANYWHERE IN THIS REPOSITORY.

Why this gate exists. An absolute path in a script, a results file or a document
names the machine the work happened to run on. Three separate costs. It is not
reproducible: a reader clones the repository and that path does not exist for
them, so a script keyed on it cannot run and a results file quoting it cannot be
traced. It leaks the author's local account name into a published artifact. And it hides
staleness: two results files can disagree simply because one was written from a
different working directory.

The rule. Anything a script records about where its input came from is a BASENAME.
Anything a script reads is built at runtime from the module's own location. A path
that must be configurable is read from an environment variable with a relative
default, never pasted in.

This check walks every shipped file and fails on a path into a user home directory,
written either way: spelled out from the root, or abbreviated to a tilde. Both name
the same place. Only the first carries the account name, and the second was invisible
here until 2026-08-20, when a shipped file was found naming a private working
directory outside this repository and this gate had been reading it and passing.
In a Git checkout the population comes from the index; in an extracted source ZIP the
shared census walks the archive. It deliberately does NOT flag /tmp, /usr, /opt or
/mnt: those are either machine-independent by convention or belong to the remote
recorder, and a location that belongs to nobody in particular leaks nothing. The same
allowance, and no wider a one, is what CONVENTIONAL_HOME_DIRS below is for.

Read-only. Exits non-zero on a finding and names file and line.

    uv run --no-project python3 checks/chk_no_abs_paths.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                         # noqa: E402
from evidence import report_gate, shipped_tree_files                    # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_no_abs_paths_results.json")

# A home-directory absolute path on macOS or Linux. The account name is captured so
# the report can say what leaked without repeating the whole path.
HOME_PATH_RE = re.compile(r"(?:/Users|/home)/([A-Za-z0-9._-]+)/")

# The same home directory written the other way, with a tilde. The two forms name the
# same place and were not the same finding here until 2026-08-20, when a line naming a
# private working directory outside this repository sat in a shipped file, reached the
# remote, and this gate read it and said PASS. The directory is captured for the same
# reason the account name is: so the report can say what was named without repeating
# the path.
HOME_TILDE_RE = re.compile(r"~/([A-Za-z0-9._-]+)")

# Directories under a home that belong to a tool rather than to a person, so that
# naming one names no machine. This is NOT the allow list below and does not work like
# it: it exempts a DIRECTORY NAME wherever it appears, never a file, and it is the same
# judgement this gate already makes when it declines to flag /tmp, /usr, /opt and /mnt.
# A tool that defines its own location under every user's home has made that location
# machine-independent by convention, and a document that names it is telling a reader
# where to put their own file, not recording where ours sits.
#
# The line this cannot draw, stated plainly rather than left for someone to discover.
# The test is a convention, and a convention is a judgement: this list is short, every
# entry carries its reason, and anything not on it is a finding. A private directory
# whose name happens to begin with a dot would pass a rule written as "dots are
# conventional", which is why that rule is not the one used here.
CONVENTIONAL_HOME_DIRS = {
    ".aws": "the shared credentials directory the AWS SDK defines for itself, in the "
            "same place under every user's home. Naming it tells a reader where their "
            "own credentials go and records nothing about the machine this ran on",
}

# Suffixes worth reading. Binary intermediates (.npz, .png, .lz4) are skipped: they
# are not text, and their provenance lives in the JSON beside them.
TEXT_SUFFIXES = (".py", ".json", ".md", ".txt", ".sh", ".ipynb", ".cfg", ".toml",
                 ".yml", ".yaml")

# Files allowed to mention a home path, each with the reason. This list should stay
# empty: a legitimate need to name a machine belongs in a document outside the published
# repository, not inside it.
ALLOW = {}


def redact(line):
    """The offending line with the home path replaced by a marker, never verbatim.

    This gate used to copy each offending line into its results file exactly as it
    stood. Two things followed and both were measured on 2026-07-31.

    Its results file is a tracked .json, so it sits inside the population this gate
    scans. A recorded finding therefore re-detected itself on the next run, quoting
    itself one escape level deeper each time, and repairing the real cause never
    cleared the gate: it stayed red about its own output, for ever, naming a line
    that no longer existed anywhere else in the tree.

    And the copy wrote the account name into a tracked file, which is the exact
    thing this gate exists to keep out of a published artifact. A gate that commits the
    leak it forbids is not a gate.

    Redaction settles both without exempting one file or narrowing the population by
    a single line: every tracked text file is still read, every match is still a
    finding, and the record still names the file, the line and the account.

    The tilde form is redacted for the same two reasons and not for weaker ones. The
    marker put in its place is deliberately not a path a home directory could hold:
    the character after the slash is outside the pattern's own alphabet, so a recorded
    finding cannot match itself when this file is scanned on the next run.
    """
    line = HOME_PATH_RE.sub("/<home>/<account>/", line.strip())
    return HOME_TILDE_RE.sub("~/<directory>", line)[:200]


def tracked_files():
    """Every file the checkout or extracted source archive ships."""
    return shipped_tree_files(ROOT)


def scan():
    findings, scanned, skipped = [], 0, 0
    for rel in tracked_files():
        if not rel.endswith(TEXT_SUFFIXES):
            skipped += 1
            continue
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().split("\n")
        except OSError as exc:
            findings.append({"file": rel, "line": 0, "rule": "UNREADABLE",
                             "detail": str(exc), "account": None, "source": ""})
            continue
        scanned += 1
        for n, line in enumerate(lines, start=1):
            if rel in ALLOW:
                continue
            m = HOME_PATH_RE.search(line)
            if m:
                findings.append({
                    "file": rel,
                    "line": n,
                    "rule": "ABS-HOME-PATH",
                    "account": m.group(1),
                    "detail": ("an absolute home path names the machine this ran on; "
                               "record a basename and build the real path at runtime "
                               "from the module's own location"),
                    "source": redact(line),
                })
            for t in HOME_TILDE_RE.finditer(line):
                if t.group(1) in CONVENTIONAL_HOME_DIRS:
                    continue
                # The directory that was named is deliberately NOT copied into this
                # record. It is the same reasoning redact() carries: this results file
                # is tracked and shipped, so writing the name here would put into a
                # published artifact the very thing the finding says does not belong in
                # one. The file and the line are the address, and they are enough.
                findings.append({
                    "file": rel,
                    "line": n,
                    "rule": "HOME-TILDE-PATH",
                    "account": None,
                    "detail": ("a tilde path names a directory that exists only on "
                               "the machine this was written on, outside this "
                               "repository; nobody who clones this can follow it, and "
                               "it advertises what else sits on that machine"),
                    "source": redact(line),
                })
                break
    return findings, scanned, skipped


def main():
    started = artifact.start_clock()
    findings, scanned, skipped = scan()
    verdict = "PASS" if not findings else "FAIL"
    results = {
        "verdict": verdict,
        "n_findings": len(findings),
        "findings": findings,
    }
    # The three records this file used to write into its own _meta -- results_file,
    # script and scope -- are now passed as parameters, because artifact.write owns
    # them. `scope` in particular changes shape rather than meaning: it was one
    # sentence, and the module asks for population, window and coins separately.
    # The counts below stay descriptive fields and travel as extra_meta.
    artifact.write(
        os.path.basename(OUT_JSON), results,
        script=__file__,
        # The tree itself is the input, and it is a list of files rather than one
        # file, so it is stated in scope instead of being hashed file by file: this
        # gate reads every shipped text file and hashing all of them here would put
        # the whole repository into its own artifact.
        inputs=[],
        scope={
            "population": f"{scanned} shipped text files scanned, "
                          f"{skipped} binaries skipped",
            "window": "n/a: this gate reads the repository as it stands now, not a "
                      "period of market data",
            "coins": "n/a: this gate reads file text and touches no market data",
        },
        started=started,
        extra_meta={
            "n_files_scanned": scanned,
            "n_files_skipped_binary": skipped,
            "allow_list": ALLOW,
            "conventional_home_dirs": CONVENTIONAL_HOME_DIRS,
        },
    )

    print("=" * 76)
    print("  NO ABSOLUTE PATHS - repository hygiene gate")
    print("=" * 76)
    print(f"  text files scanned : {scanned}")
    print(f"  binaries skipped   : {skipped}")
    print(f"  findings           : {len(findings)}")
    for f in findings:
        named = (f"account {f['account']}" if f.get("account")
                 else "a home directory written with a tilde; open the line to read "
                      "which one, it is not copied into a shipped file")
        print(f"  {f['rule']:16} {f['file']}:{f['line']}  ({named})")
        print(f"      | {f['source']}")
    print("-" * 76)
    print(f"  VERDICT: {verdict}")
    print(f"  results -> {os.path.basename(OUT_JSON)}")
    # The list above is the fact and the place; what it never carried was the
    # expectation, so a red run said "FAIL" and left the reader to infer from a
    # regex name why a path in a file is a defect at all. The ceiling is zero and
    # is written here rather than held in a constant, because a named ceiling is a
    # dial and this rule has none: the ALLOW map above is empty and stays empty.
    abs_home = [f for f in findings if f["rule"] != "HOME-TILDE-PATH"]
    tilde = [f for f in findings if f["rule"] == "HOME-TILDE-PATH"]
    return report_gate(
        [{"name": "ABS-HOME-PATH",
          "permitted": 0,
          "found": len(abs_home),
          "assumption": ("no file this repository tracks names a home directory. "
                         "The path does not exist for the reader who clones "
                         "this, so the script will not run and the number cannot "
                         "be traced; it carries the local account name into a "
                         "published artifact; and two results files can disagree for "
                         "no reason beyond having been written from two "
                         "directories"),
          # Spelled from the compiled pattern rather than typed out, so this line
          # cannot itself become a finding and cannot drift from the rule it
          # describes.
          "method": (f"the pattern {HOME_PATH_RE.pattern} over every line of every "
                     "shipped file whose suffix is in "
                     + ", ".join(TEXT_SUFFIXES)),
          "note": ("record a basename, and build the real path at run time from "
                   "the module's own location"),
          "sites": abs_home},
         {"name": "HOME-TILDE-PATH",
          "permitted": 0,
          "found": len(tilde),
          "assumption": ("no file this repository tracks names a home directory "
                         "under a tilde either. The tilde hides the account name, so "
                         "this costs less than the form above, and it costs the other "
                         "two things in full: the directory exists on one machine "
                         "only, so a reader who clones this cannot follow the "
                         "reference, and naming it says out loud what else that "
                         "machine holds. Until 2026-08-20 this gate read the two "
                         "forms differently and passed a tree that named a private "
                         "working directory in a shipped file"),
          # Spelled from the compiled pattern for the same reason as the rule above.
          "method": (f"the pattern {HOME_TILDE_RE.pattern} over the same lines, "
                     f"less the directories a tool defines for itself under every "
                     f"user's home: " + ", ".join(sorted(CONVENTIONAL_HOME_DIRS))),
          "note": ("name the thing rather than its place: say which tool or which "
                   "public source, and let the reader find it on their own machine"),
          "sites": tilde}],
        OUT_JSON, inputs={"tree": "shared checkout/archive shipped-tree census"})


if __name__ == "__main__":
    sys.exit(main())
