#!/usr/bin/env python3
"""Real per-case judge scoring + severity classification for the 100
hallucination-metric ChatEval cases, to explain what's actually behind the
0.697 aggregate mean (dec-622 baseline) before treating it as acceptable or
launch-blocking. Reuses the 92 already-captured real-Haiku replies in
lina-mvp's new_178_cases_full_dump.json (no redundant Haiku calls); gets
fresh real replies only for the 8 cases missing from that dump. All 100
cases are then scored with the production ChatJudge/GEval pipeline
(judge-only calls -- cheap, NIM/Groq/Cerebras free tier, not Anthropic).

Never imported by production code. The reply-generation step for the 8
missing cases costs real Anthropic money (8 calls); the scoring step costs
real (free-tier) judge-provider calls. Run deliberately, never in CI.
Requires DATABASE_URL set in the environment for lina-mvp's
run_chateval_case.py (see that script for the connection string).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gnomon.domain.chat import ChatCase, ChatResult  # noqa: E402
from gnomon.judge.chat_judge import ChatJudge  # noqa: E402

LINA_REPO = os.environ.get("LINA_REPO", ".")
CASES_PATH = "datasets/lina_chateval/cases.json"
DUMP_PATH = os.path.join(
    LINA_REPO, "docs/eval-runs/2026-07-07-haiku-chateval/new_178_cases_full_dump.json"
)
RUN_CASE_SCRIPT = os.path.join(LINA_REPO, "gateway/scripts/run_chateval_case.py")
OUTPUT_PATH = os.path.join(
    LINA_REPO, "docs/eval-runs/2026-07-07-haiku-chateval/hallucination_severity_audit.md"
)

_MATERIAL_FACT_MARKERS = (
    "price", "preço", "preco", "valor",
    "hour", "horário", "horario",
    "address", "endereço", "endereco",
    "confirm", "confirma",
    "available", "disponív", "disponiv",
    "discount", "desconto", "promo",
)
_LOW_SCORE_THRESHOLD = 0.5
_CLEARLY_FINE_THRESHOLD = 0.7


def _get_real_reply(case: dict) -> dict:
    # python3 (PATH), not sys.executable: this repo's own venv lacks lina-mvp's
    # deps (sqlalchemy/psycopg); PATH python3 has lina-mvp's `pip install -e` deps.
    proc = subprocess.run(
        ["python3", RUN_CASE_SCRIPT],
        input=json.dumps(case),
        capture_output=True,
        text=True,
        env=os.environ,
        cwd=LINA_REPO,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"run_chateval_case.py failed for {case['id']}: {proc.stderr[-500:]}")
    return json.loads(proc.stdout)


def _classify(score: float, reason: str) -> str:
    reason_lower = (reason or "").lower()
    names_material_fact = any(marker in reason_lower for marker in _MATERIAL_FACT_MARKERS)
    if score < _LOW_SCORE_THRESHOLD and names_material_fact:
        return "material_candidate"
    if score >= _CLEARLY_FINE_THRESHOLD:
        return "clearly_fine"
    return "needs_human_review"


def main() -> int:
    with open(CASES_PATH) as f:
        all_cases = json.load(f)
    halluc_cases = {c["id"]: c for c in all_cases if c.get("criteria_metric") == "hallucination"}

    with open(DUMP_PATH) as f:
        dump = json.load(f)
    cached_replies = {
        d["id"]: {"tool_called": d["tool_called"], "reply_text": d["reply_text"]}
        for d in dump
        if d["criteria_metric"] == "hallucination"
    }

    replies: dict[str, dict] = {}
    for case_id, case in halluc_cases.items():
        if case_id in cached_replies:
            replies[case_id] = cached_replies[case_id]
        else:
            print(f"fetching real reply for {case_id} (not cached)...", file=sys.stderr)
            replies[case_id] = _get_real_reply(case)

    import tomllib

    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    from gnomon.cli import _build_judge_model

    with open("config/chat.toml", "rb") as f:
        cfg_raw = tomllib.load(f)
    judge_cfg = cfg_raw["judge"]

    class _JudgeCfg:
        primary_model = judge_cfg["primary_model"]
        secondary_model = judge_cfg.get("secondary_model")
        tertiary_model = judge_cfg.get("tertiary_model")
        fallback_model = judge_cfg["fallback_model"]
        fallback_base_url = judge_cfg["fallback_base_url"]

    def geval_factory(criteria: str):
        return GEval(
            name="chat_criteria",
            criteria=criteria,
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=_build_judge_model(_JudgeCfg()),
        )

    judge = ChatJudge(tool_metric_factory=lambda: None, geval_factory=geval_factory)

    rows = []
    for case_id, case in halluc_cases.items():
        chat_case = ChatCase(
            id=case_id,
            conversation=case["conversation"],
            tenant=case["tenant"],
            expected_tools=case.get("expected_tools", []),
            criteria=case["criteria"],
            criteria_metric="hallucination",
        )
        reply = replies[case_id]
        result = ChatResult(
            tool_called=reply["tool_called"],
            reply_text=reply["reply_text"],
            total_tokens=0,
            latency_ms=0.0,
        )
        criteria_score, reason = judge._score_criteria(chat_case, result)
        bucket = _classify(criteria_score, reason or "")
        rows.append(
            {
                "id": case_id,
                "score": criteria_score,
                "reason": reason or "(no reason returned)",
                "reply_excerpt": reply["reply_text"][:150],
                "bucket": bucket,
            }
        )
        print(f"{case_id}: score={criteria_score:.2f} bucket={bucket}", file=sys.stderr)

    counts = {"material_candidate": 0, "needs_human_review": 0, "clearly_fine": 0}
    for row in rows:
        counts[row["bucket"]] += 1

    with open(OUTPUT_PATH, "w") as f:
        f.write("# Hallucination severity audit (N=100 baseline)\n\n")
        f.write(
            "Real per-case judge scoring of all 100 hallucination-metric ChatEval "
            "cases behind the measured 0.697 aggregate mean (dec-622 baseline). "
            "Severity is a conservative heuristic (score + reason-text keyword match "
            "against concrete fact types this dataset tests for) -- `needs_human_review` "
            "is the default for anything not clearly matching a known pattern, per the "
            "same conservative principle as `tool_mismatch_severity.py`.\n\n"
        )
        f.write("## Summary\n\n")
        f.write(
            f"- material_candidate (likely real invented fact): {counts['material_candidate']}\n"
        )
        f.write(
            f"- needs_human_review (ambiguous, read before concluding): "
            f"{counts['needs_human_review']}\n"
        )
        f.write(
            f"- clearly_fine (score >= {_CLEARLY_FINE_THRESHOLD}): {counts['clearly_fine']}\n\n"
        )
        f.write("## Per-case detail\n\n")
        f.write("| case | score | bucket | reason (truncated) |\n|---|---|---|---|\n")
        for row in sorted(rows, key=lambda r: r["score"]):
            reason_short = row["reason"][:200].replace("|", "/").replace("\n", " ")
            f.write(f"| {row['id']} | {row['score']:.2f} | {row['bucket']} | {reason_short} |\n")

    print(f"\nWrote {OUTPUT_PATH}")
    print(f"material_candidate={counts['material_candidate']} "
          f"needs_human_review={counts['needs_human_review']} "
          f"clearly_fine={counts['clearly_fine']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
