"""Command line: python -m crew {models,plan,build,run}"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import load_config
from .llm import LLM
from .orchestrator import Crew

HERE = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crew", description="Turn a one-page spec into tested Python with local models.")
    ap.add_argument("--config", type=Path, default=HERE / "crew.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models", help="list the model ids LM Studio offers")
    p = sub.add_parser("plan", help="spec -> requirements and design, then stop for your review")
    p.add_argument("spec", type=Path)
    p = sub.add_parser("build", help="approved plan -> code, tests, fix loop, report")
    p.add_argument("run_dir", type=Path)
    p = sub.add_parser("run", help="plan and build in one go, no review stop")
    p.add_argument("spec", type=Path)
    args = ap.parse_args(argv)

    cfg = load_config(args.config, require_model=args.cmd != "models")

    if args.cmd == "models":
        print("\n".join(LLM(cfg).list_models()))
        return 0

    if args.cmd == "build":
        run_dir = args.run_dir
    else:
        run_dir = HERE / "runs" / f"{args.spec.stem}-{time.strftime('%Y%m%d-%H%M%S')}"
    crew = Crew(cfg, LLM(cfg, log_dir=run_dir / "logs"), run_dir)

    if args.cmd in ("plan", "run"):
        plan_md = crew.plan(args.spec.read_text(encoding="utf-8"))
        if args.cmd == "plan":
            print(f"\nPlan written to {plan_md}\nReview it (edit plan.json / requirements.json beside it "
                  f"if needed), then:\n  python -m crew build {run_dir}")
            return 0

    ok = crew.build()
    print(f"\n{'Tests pass.' if ok else 'Tests still failing.'} Report: {run_dir / 'REPORT.md'}\n"
          f"Code: {run_dir / 'project'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
