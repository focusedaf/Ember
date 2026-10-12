import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("preprocess", "src/preprocess.py"),
    ("analytics", "src/analytics.py"),
    ("spark", "src/spark_analytics.py"),
    ("findings", "src/generate_findings.py"),
    ("charts", "src/visualizations.py"),
]


def main():
    names = [n for n, _ in STEPS]
    parser = argparse.ArgumentParser(description="Run the EMBER pipeline end to end.")
    parser.add_argument("--only", nargs="+", choices=names, help="run only these steps")
    parser.add_argument("--skip", nargs="+", choices=names, default=[], help="skip these steps")
    args = parser.parse_args()

    selected = [(n, p) for n, p in STEPS
                if (not args.only or n in args.only) and n not in args.skip]
    results = []
    for name, rel in selected:
        print(f"\n=== {name}: python {rel} ===", flush=True)
        start = time.perf_counter()
        code = subprocess.run([sys.executable, str(ROOT / rel)], cwd=ROOT).returncode
        results.append((name, code, time.perf_counter() - start))
        if code != 0:
            print(f"\nStep '{name}' failed with exit code {code}. Stopping.")
            break

    print("\nPipeline summary")
    for name, code, secs in results:
        print(f"  {name:<11} {'OK' if code == 0 else 'FAILED':<7} {secs:6.1f}s")
    if any(code != 0 for _, code, _ in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()