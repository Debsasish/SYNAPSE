"""One-command reproduction of the entire SYNAPSE research artifact.

Runs, in order:
  1. Conformance/unit tests (fail fast if the implementation is broken).
  2. Scale-invariance experiment  -> results/scale_*.csv
  3. Resolver-quality experiment   -> results/resolver_quality.csv, ablation.csv, ...
  4. Figure generation             -> figures/*.png, *.pdf

Everything is deterministic and offline. Usage:

    python run_all.py            # full run
    python run_all.py --quick    # smaller grid for a fast smoke test
"""
from __future__ import annotations
import os
import sys
import time
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([SRC, ROOT, env.get("PYTHONPATH", "")])
    env.setdefault("SYNAPSE_QUICK", "0")
    return env


def _run(title: str, args: list[str], env: dict) -> None:
    print(f"\n{'='*70}\n{title}\n{'='*70}", flush=True)
    t0 = time.time()
    proc = subprocess.run([sys.executable, "-u", *args], cwd=ROOT, env=env)
    dt = time.time() - t0
    if proc.returncode != 0:
        print(f"\n[FAILED] {title} (exit {proc.returncode})", flush=True)
        sys.exit(proc.returncode)
    print(f"[ok] {title} in {dt:.1f}s", flush=True)


def main() -> None:
    quick = "--quick" in sys.argv
    env = _env()
    if quick:
        env["SYNAPSE_QUICK"] = "1"

    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "figures"), exist_ok=True)

    _run("1/4  Conformance tests", ["-m", "pytest", "-q", "tests/"], env)
    _run("2/4  Scale-invariance experiment", ["-m", "benchmarks.run_scale_invariance"], env)
    _run("3/4  Resolver-quality experiment", ["-m", "benchmarks.run_resolver_quality"], env)
    _run("4/4  Figures", ["-m", "scripts.make_figures"], env)

    print(f"\n{'='*70}\nAll steps complete. See results/ and figures/.\n{'='*70}", flush=True)


if __name__ == "__main__":
    main()
