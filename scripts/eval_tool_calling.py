"""
LLM tool calling 평가 스크립트

ConversationService와 같은 시스템 프롬프트와 도구 선언을 그대로 써서,
질의마다 모델이 "어떤 도구를, 어떤 인자로" 고르는지만 확인한다.
도구를 실제로 실행하지 않으므로 DB 연결이 필요 없다. (.env의 GEMINI_API_KEY만 사용)

사용법 (레포 루트에서):
    python scripts/eval_tool_calling.py
    python scripts/eval_tool_calling.py --repeat 3     # 3번씩 돌려 일관성 확인
    python scripts/eval_tool_calling.py --only tag-01  # 특정 케이스만
    python scripts/eval_tool_calling.py \
        --cases scripts/eval_tool_calling_cases_hard.json
"""

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.conversation_service import (  # noqa: E402
    SEARCH_PLACES_DECLARATION,
    SEARCH_TOUR_PLACES_DECLARATION,
    SYSTEM_PROMPT,
)

MODEL = "gemini-3.6-flash"  # ConversationService와 같은 모델로 맞출 것
CASES_PATH = Path(__file__).with_name("eval_tool_calling_cases.json")
RESULT_DIR = ROOT / "eval_results"

CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[
        types.Tool(
            function_declarations=[
                SEARCH_PLACES_DECLARATION,
                SEARCH_TOUR_PLACES_DECLARATION,
            ]
        )
    ],
)


# ------------------------------------------------------------
# 모델 호출
# ------------------------------------------------------------
def build_contents(case: dict) -> list[types.Content]:
    contents = [
        types.Content(
            role=turn["role"], parts=[types.Part.from_text(text=turn["text"])]
        )
        for turn in case.get("history", [])
    ]
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=case["query"])])
    )
    return contents


async def call_model(client: genai.Client, contents, max_retries: int = 4):
    """429(요청 한도 초과)면 지수 백오프로 재시도한다."""
    delay = 5.0
    for attempt in range(max_retries):
        try:
            return await client.aio.models.generate_content(
                model=MODEL, contents=contents, config=CONFIG
            )
        except errors.APIError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(f"    429 받음, {delay:.0f}초 후 재시도")
                await asyncio.sleep(delay)
                delay *= 2
                continue
            raise


def extract_calls(response) -> list[tuple[str, dict]]:
    """응답에 담긴 function call을 전부 꺼낸다. (서비스는 현재 첫 번째만 실행)"""
    candidates = response.candidates or []
    if not candidates or not candidates[0].content or not candidates[0].content.parts:
        return []
    return [
        (part.function_call.name, dict(part.function_call.args or {}))
        for part in candidates[0].content.parts
        if part.function_call
    ]


# ------------------------------------------------------------
# 채점
# ------------------------------------------------------------
def _norm(s: str) -> str:
    return (s or "").replace(" ", "").replace("동", "").replace("역", "")


def grade(expect: dict, calls: list[tuple[str, dict]]) -> dict:
    tool, args = calls[0] if calls else (None, {})
    checks = {"tool": tool == expect["tool"]}
    if "all_tools" in expect:
        # 도구를 여러 개 불러야 하는 질의: 첫 호출의 순서와 상관없이 전부 불렀는지 확인
        called = {name for name, _ in calls}
        checks["tool"] = called == set(expect["all_tools"])
        tool, args = next(
            ((n, a) for n, a in calls if n == expect["tool"]), (tool, args)
        )

    if checks["tool"] and expect["tool"] is not None:
        exp_region, act_region = _norm(expect["region"]), _norm(args.get("region", ""))
        checks["region"] = bool(act_region) and (
            exp_region in act_region or act_region in exp_region
        )

        if "category" in expect:
            checks["category"] = args.get("category") == expect["category"]

        if "tags" in expect:
            exp_tags = set(expect["tags"])
            act_tags = set(args.get("tags") or [])
            # 기대 태그가 있으면 포함돼야 하고, 없으면 아무 태그도 채우지 않아야 정답
            checks["tags"] = exp_tags <= act_tags if exp_tags else not act_tags

    checks["passed"] = all(checks.values())
    return checks


# ------------------------------------------------------------
# 실행
# ------------------------------------------------------------
async def run(repeat: int, only: str | None, interval: float, cases_path: Path):
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if only:
        cases = [c for c in cases if c["id"] == only]

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    records = []

    for case in cases:
        for i in range(repeat):
            started = time.perf_counter()
            try:
                response = await call_model(client, build_contents(case))
                calls = extract_calls(response)
                error = None
            except Exception as e:  # 한 케이스 실패가 전체 평가를 멈추지 않게
                calls, error = [], repr(e)
            latency_ms = (time.perf_counter() - started) * 1000

            checks = grade(case["expect"], calls) if not error else {"passed": False}
            records.append(
                {
                    "id": case["id"],
                    "group": case["group"],
                    "query": case["query"],
                    "run": i + 1,
                    "expect": case["expect"],
                    "actual": [{"tool": n, "args": a} for n, a in calls] or None,
                    "checks": checks,
                    "latency_ms": round(latency_ms),
                    "error": error,
                }
            )
            mark = "PASS" if checks["passed"] else "FAIL"
            shown = calls or "도구 호출 없음"
            print(f"[{mark}] {case['id']} #{i + 1} {case['query']} -> {shown}")
            await asyncio.sleep(interval)

    summarize(records, repeat)
    save(records)


def summarize(records: list[dict], repeat: int):
    total = len(records)
    passed = sum(r["checks"]["passed"] for r in records)
    print("\n" + "=" * 60)
    print(f"전체 정확도: {passed}/{total} ({passed / total:.0%})")

    field_hits, field_total = defaultdict(int), defaultdict(int)
    for r in records:
        for field, ok in r["checks"].items():
            if field == "passed":
                continue
            field_total[field] += 1
            field_hits[field] += ok
    for field in ["tool", "region", "category", "tags"]:
        if field_total[field]:
            print(
                f"  {field:<9}: {field_hits[field]}/{field_total[field]} "
                f"({field_hits[field] / field_total[field]:.0%})"
            )

    print("\n그룹별")
    by_group = defaultdict(list)
    for r in records:
        by_group[r["group"]].append(r["checks"]["passed"])
    for group, results in by_group.items():
        print(f"  {group:<14}: {sum(results)}/{len(results)}")

    latencies = sorted(r["latency_ms"] for r in records if not r["error"])
    if latencies:
        p50 = latencies[len(latencies) // 2]
        print(f"\n응답 시간 p50 {p50}ms, 최대 {latencies[-1]}ms (429 재시도 대기 포함)")

    if repeat > 1:
        by_case = defaultdict(set)
        for r in records:
            by_case[r["id"]].add(
                json.dumps(r["actual"], ensure_ascii=False, sort_keys=True)
            )
        unstable = [cid for cid, outs in by_case.items() if len(outs) > 1]
        print(f"\n반복 실행 시 결과가 달라진 케이스: {len(unstable)}개 {unstable}")

    failures = [r for r in records if not r["checks"]["passed"]]
    if failures:
        print("\n실패 케이스")
        for r in failures:
            print(f'  - {r["id"]} "{r["query"]}"')
            print(f"      기대: {r['expect']}")
            print(
                f"      실제: {r['actual']}"
                + (f"  (에러: {r['error']})" if r["error"] else "")
            )


def save(records: list[dict]):
    RESULT_DIR.mkdir(exist_ok=True)
    path = RESULT_DIR / f"tool_calling_{datetime.now():%Y%m%d_%H%M%S}.json"  # noqa: DTZ005
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=1, help="케이스당 반복 횟수")
    parser.add_argument("--only", type=str, default=None, help="특정 케이스 id만 실행")
    parser.add_argument("--interval", type=float, default=1.0, help="호출 간 대기(초)")
    parser.add_argument(
        "--cases", type=Path, default=CASES_PATH, help="평가 케이스 JSON 경로"
    )
    opts = parser.parse_args()
    asyncio.run(run(opts.repeat, opts.only, opts.interval, opts.cases))