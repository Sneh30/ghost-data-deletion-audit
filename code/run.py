"""End-to-end runner: load evidence, reconstruct state, plan, serialize."""
from __future__ import annotations

import argparse
import pickle
import sys
from collections import Counter
from pathlib import Path

from .evidence import EvidenceExtractor
from .loader import load_dataset
from .planner import plan_case
from .serialize import write_output
from .state import StateBuilder


ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "facts.pkl"


def extract_facts(root: Path, refresh: bool = False):
    if CACHE.exists() and not refresh:
        with CACHE.open("rb") as handle:
            return pickle.load(handle)
    ds = load_dataset(root)
    extractor = EvidenceExtractor(ds)
    facts = extractor.extract_all()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("wb") as handle:
        pickle.dump(facts, handle)
    return facts


def build_rows(root: Path, facts, mode: str = "eval") -> list[dict]:
    ds = load_dataset(root)
    builder = StateBuilder(ds, facts)
    if mode == "sample":
        cases = [c for c in builder.cases if c.sample]
    elif mode == "all":
        cases = list(builder.cases)
    else:
        cases = [c for c in builder.cases if not c.sample]
    rows = []
    for case in cases:
        state = builder.build(case)
        if state is None:
            raise RuntimeError(f"could not resolve identity for {case.case_id}")
        status, steps = plan_case(state)
        rows.append(
            {
                "case_id": case.case_id,
                "deletion_status": status,
                "steps": steps,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ghost Data Deletion Audit Agent")
    parser.add_argument("--root", default=str(ROOT), help="repository root")
    parser.add_argument("--out", default=str(ROOT / "output.csv"), help="output CSV path")
    parser.add_argument("--refresh", action="store_true", help="re-extract evidence facts")
    parser.add_argument("--samples", action="store_true", help="run the 32 public samples")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    facts = extract_facts(root, refresh=args.refresh)
    rows = build_rows(root, facts, mode="sample" if args.samples else "eval")
    write_output(rows, args.out)
    counts = Counter(row["deletion_status"] for row in rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    print("status counts:", dict(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
