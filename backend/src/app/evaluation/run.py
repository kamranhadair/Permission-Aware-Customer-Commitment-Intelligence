"""Canonical Milestone 6 evaluation CLI entry point.

    python -m app.evaluation.run --mode security
    python -m app.evaluation.run --mode retrieval
    python -m app.evaluation.run --mode generation --limit 15
    python -m app.evaluation.run --mode generation --resume
    python -m app.evaluation.run --review-case-id ce-01 --review-gate hidden_conflict_leakage --review-verdict pass

Replaces the retired `app.retrieval.evaluate` / `app.generation.evaluate`
scripts (Milestone 4/5) — this is now the single evaluation command; see
docs/evaluation.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# GeminiAnswerGenerator reads GEMINI_API_KEY from the process environment
# directly (app/generation/provider.py), and nothing outside conftest.py's
# test-only setup loads backend/.env into os.environ — so --mode generation
# would otherwise require manually exporting the key in every shell despite
# .env.example documenting it as the configuration source. Mirrors
# conftest.py's exact load_dotenv call; override=False so a real shell env
# var still wins.
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env", override=False)

from app.evaluation import report, runner  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["security", "retrieval", "generation"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-dir", default=str(runner.DEFAULT_OUTPUT_DIR))
    parser.add_argument("--review-case-id", default=None)
    parser.add_argument("--review-gate", choices=["unauthorized_fact_emitted", "hidden_conflict_leakage"], default=None)
    parser.add_argument("--review-verdict", choices=["pass", "fail"], default=None)
    parser.add_argument("--review-note", default=None)
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)

    if args.review_case_id:
        if not (args.review_gate and args.review_verdict):
            parser.error("--review-case-id requires --review-gate and --review-verdict")
        runner.mark_reviewed(output_dir, args.review_case_id, args.review_gate, args.review_verdict, args.review_note)
        print(f"Recorded {args.review_gate}={args.review_verdict} for {args.review_case_id}")
        return 0

    if not args.mode:
        parser.error("--mode is required unless using --review-case-id")

    result = runner.run(
        mode=args.mode,
        limit=args.limit,
        start_at=args.start_at,
        case_id=args.case_id,
        resume=args.resume,
        output_dir=output_dir,
    )
    print(report.render(result))

    if not result.security_all_clear:
        print()
        print("SECURITY GATE FAILED: one or more automated structural gates reported a violation.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
