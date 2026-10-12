#!/usr/bin/env python3
"""
正答率テスト（ステップ2）

evals/cases/ の各問題を、エージェントに N 回ずつ解かせて採点する。

採点ルール（機械的に判定）:
  - 判定一致 : 回答の「判定：〜」が case.json の expected と一致
  - 要点     : must_mention の正規表現が「すべて」回答に含まれる
  - 禁止語   : must_not_mention が「1つも」含まれない（インジェクション対策の確認）
  - 正答     : 上の3つをすべて満たしたもの

使い方:
  export MODEL_ID=jp.anthropic.claude-sonnet-4-6
  python run_eval.py              # 全問 × 3回
  python run_eval.py --runs 1     # お試し（全問 × 1回）
  python run_eval.py --case case05_injection --runs 5
  python run_eval.py --bare       # 工夫なし（システムプロンプトを外した素のモデル）で比較
"""
import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from strands import Agent
from strands.models import BedrockModel

import agent as A  # agent.py のツール・システムプロンプトをそのまま使う

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "evals" / "cases"
RESULTS_DIR = HERE / "evals" / "results"

VERDICTS = ["不具合", "仕様どおり", "環境要因"]
ANSWER_FORMAT = (
    "\n\n回答の最後の行には、次のどれか1つを必ず書いてください。\n"
    "判定：不具合 ／ 判定：仕様どおり ／ 判定：環境要因"
)
VERDICT_RE = re.compile(r"判定\s*[:：]\s*\**\s*(不具合|仕様どおり|環境要因)")


def load_cases(only=None):
    cases = []
    for d in sorted(CASES_DIR.iterdir()):
        if not (d / "case.json").exists() or (only and d.name != only):
            continue
        c = json.loads((d / "case.json").read_text(encoding="utf-8"))
        c["id"] = d.name
        c["repo"] = d / "repo"
        cases.append(c)
    return cases


def grade(answer: str, case: dict) -> dict:
    found = VERDICT_RE.findall(answer)
    verdict = found[-1] if found else "（なし）"
    points_ok = all(re.search(p, answer, re.IGNORECASE) for p in case.get("must_mention", []))
    forbidden = [p for p in case.get("must_not_mention", []) if re.search(p, answer, re.IGNORECASE)]
    verdict_ok = verdict == case["expected"]
    return {
        "verdict": verdict,
        "verdict_ok": verdict_ok,
        "points_ok": points_ok,
        "forbidden_hit": ",".join(forbidden),
        "correct": verdict_ok and points_ok and not forbidden,
    }


def tool_calls(result) -> int:
    try:
        return sum(m.call_count for m in result.metrics.tool_metrics.values())
    except Exception:
        return -1


BARE_PROMPT = "あなたはアシスタントです。"  # 比較用：ルールを何も与えない


def run_once(case: dict, model_id: str, region: str, system_prompt: str):
    A.ROOT = case["repo"].resolve()  # ツールが読める範囲を、この問題のフォルダだけにする
    ag = Agent(
        model=BedrockModel(model_id=model_id, region_name=region),
        system_prompt=system_prompt,
        tools=[A.list_files, A.read_file, A.grep],
        callback_handler=None,  # 途中経過を画面に流さない
    )
    t0 = time.time()
    result = ag(case["question"] + ANSWER_FORMAT)
    return str(result), tool_calls(result), round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--case", default=None)
    ap.add_argument("--bare", action="store_true", help="システムプロンプトを外して比較する")
    args = ap.parse_args()

    if not A.MODEL_ID:
        raise SystemExit("MODEL_ID を設定してください（例: export MODEL_ID=jp.anthropic.claude-sonnet-4-6）")

    cases = load_cases(args.case)
    stamp = datetime.now().strftime("%Y%m%d-%H%M") + ("-bare" if args.bare else "")
    system_prompt = BARE_PROMPT if args.bare else A.SYSTEM_PROMPT
    mode = "素のモデル（工夫なし）" if args.bare else "工夫あり"
    print(f"モード: {mode}\n")
    out_dir = RESULTS_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for c in cases:
        for r in range(1, args.runs + 1):
            print(f"▶ {c['id']} ({r}/{args.runs}) ... ", end="", flush=True)
            answer, n_tools, sec, error = None, -1, 0, ""
            for attempt, wait in enumerate([0, 20, 40, 60]):  # 失敗したら待って最大3回やり直す
                if wait:
                    print(f"\n   …エラーのため{wait}秒待って再試行（{attempt}/3） ", end="", flush=True)
                    time.sleep(wait)
                try:
                    answer, n_tools, sec = run_once(c, A.MODEL_ID, A.REGION, system_prompt)
                    error = ""
                    break
                except Exception as e:
                    error = f"{type(e).__name__}: {e}"
            (out_dir / f"{c['id']}_{r}.md").write_text(answer or f"ERROR: {error}", encoding="utf-8")
            if error:
                print(f"⚠ 実行エラー（採点対象外）: {error[:120]}")
                rows.append({"case": c["id"], "run": r, "expected": c["expected"], "verdict": "",
                             "verdict_ok": False, "points_ok": False, "forbidden_hit": "",
                             "correct": False, "error": error[:300], "tool_calls": -1, "seconds": 0})
                continue
            g = grade(answer, c)
            print(("○" if g["correct"] else "×") + f"  判定={g['verdict']}  ツール{n_tools}回  {sec}秒")
            rows.append({"case": c["id"], "run": r, "expected": c["expected"],
                         **g, "error": "", "tool_calls": n_tools, "seconds": sec})
            time.sleep(3)  # 連続呼び出しで上限に当たりにくくする

    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n=== 結果（実行エラーの回は除外） ===")
    print(f"{'問題':<22}{'正答':>8}{'判定一致':>10}{'エラー':>8}")
    for c in cases:
        rs = [x for x in rows if x["case"] == c["id"]]
        done = [x for x in rs if not x["error"]]
        ok = sum(x["correct"] for x in done)
        vok = sum(x["verdict_ok"] for x in done)
        print(f"{c['id']:<22}{ok:>4}/{len(done):<4}{vok:>6}/{len(done):<4}{len(rs) - len(done):>4}")
    done = [x for x in rows if not x["error"]]
    total = sum(x["correct"] for x in done)
    rate = f"{total / len(done):.0%}" if done else "-"
    print(f"\n正答率: {total}/{len(done)} = {rate}   （{mode} / 実行エラー {len(rows) - len(done)}回 / モデル: {A.MODEL_ID}）")
    print(f"回答と results.csv の保存先: {out_dir}")


if __name__ == "__main__":
    main()
