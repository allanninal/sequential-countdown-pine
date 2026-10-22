# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 (see LICENSE)
"""Check pine/SequentialCountdown.pine against tests/reference.py, bar by bar, with PineTS (a local Pine v6 runtime).

    cd tests/runner && npm install && cd ../..
    python3 tests/check_pine.py <bars dir>
<bars dir> holds <SYMBOL>_<TF>.csv files with the columns time (unix ms), open, high, low, close[, volume], oldest first.

Parity: the four count plots the script shows in the Data Window (buy/sell setup count with 10 = perfected 9, buy/sell
countdown number with -1 = deferred) equal the reference's on every bar, for each configuration below. Repaint: the
script is re-run on the series cut at three points; every bar before a cut must read the same as in the full run (a
closed bar never changes when later bars arrive)."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reference import run  # noqa: E402

PINE = HERE.parent / "pine" / "SequentialCountdown.pine"
RUNNER = HERE / "runner" / "run_pine.mjs"
PLOTS = ["Buy setup count (9 = complete, 10 = perfected 9)", "Sell setup count (9 = complete, 10 = perfected 9)",
         "Buy countdown number (-1 = deferred)", "Sell countdown number (-1 = deferred)"]
# tag: PineTS input overrides keyed by input title (the display switches must not change any count)
CONFIGS = {
    "default": {},
    "numbers_off": {"Show setup numbers 1-8": False, "Show the countdown 1-13": False},
}


def pine_run(bars_csv, inputs):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as t:
        out = t.name
    cmd = ["node", str(RUNNER), str(PINE), str(bars_csv), out]
    for k, v in inputs.items():
        cmd += ["--input", f"{k}={str(v).lower() if isinstance(v, bool) else v}"]
    subprocess.run(cmd + PLOTS, check=True, capture_output=True, text=True)
    d = pd.read_csv(out)
    os.unlink(out)
    return [d[p].fillna(-99).astype(int).to_numpy() for p in PLOTS]


def expected(b):
    rows = run(*(b[k].to_numpy(float) for k in ("high", "low", "close")))
    return [np.array([10 if r["ev_setup"] == 1 and r["perf"] else r["bcnt"] for r in rows]),
            np.array([10 if r["ev_setup"] == -1 and r["perf"] else r["scnt"] for r in rows]),
            np.array([-1 if r["defer"] == 1 else r["bmark"] for r in rows]),
            np.array([-1 if r["defer"] == -1 else r["smark"] for r in rows])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    a = ap.parse_args()
    series = sorted(Path(a.bars).glob("*.csv"))
    ok = True
    for tag, inputs in CONFIGS.items():
        nines = thirteens = bad = 0
        for f in series:
            b = pd.read_csv(f)
            got = pine_run(f, inputs)
            exp = expected(b)
            nines += int(np.isin(exp[0], (9, 10)).sum() + np.isin(exp[1], (9, 10)).sum())
            thirteens += int((exp[2] == 13).sum() + (exp[3] == 13).sum())
            for p, g, e in zip(PLOTS, got, exp):
                miss = np.where(g != e)[0]
                bad += len(miss)
                for i in miss[:3]:
                    print(f"  {tag} {f.stem} {p} bar {i}: pine {g[i]} reference {e[i]}")
        print(f"parity {tag}: {len(series)} series, {nines} nines, {thirteens} thirteens, {bad} mismatches")
        ok &= bad == 0
    # repaint: cut each series at three points and compare with the full run (default inputs)
    changed = checked = 0
    for f in series:
        b = pd.read_csv(f)
        full = pine_run(f, {})
        n = len(b)
        for cut in (n // 2, n - 300, n - 1):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as t:
                b.iloc[:cut].to_csv(t, index=False)
            part = pine_run(t.name, {})
            os.unlink(t.name)
            for g, fu in zip(part, full):
                checked += cut
                changed += int((g[:cut] != fu[:cut]).sum())
    print(f"repaint: {checked} bar values re-read after cuts, {changed} changed")
    ok &= changed == 0
    print("ALL PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
