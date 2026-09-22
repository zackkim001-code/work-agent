#!/usr/bin/env python3
"""할 일 목록에 기한·방치 지표를 붙이고 우선순위 후보를 고른다.

입력 (stdin, JSON 배열): notion-store rows 모드로 조회한 할 일.
  필요한 키: id|url, 제목, 구분, 상태, 기한(YYYY-MM-DD|null), 최근 언급일(YYYY-MM-DD|null), 프로젝트(이름)
출력 (stdout, JSON):
  {
    "today": "...",
    "tasks": [ {...원본, "days_to_due": int|null, "days_since_mention": int|null,
                "flags": ["기한 경과","기한 임박","방치"], "score": int} ],
    "today_candidates": [...],   # score 기준 상위, 명시 우선
    "stale": [...]               # 방치 (최근 언급 후 14일 초과)
  }

옵션:
  --today YYYY-MM-DD   기준일 (기본: 오늘, KST 가정)
  --stale-days N       방치 기준 (기본 14)
  --max N              오늘 후보 최대 건수 (기본 7)
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

# Windows 기본 인코딩(cp949)에서 한국어 키가 깨지므로 UTF-8로 고정
for _s in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

KST = timezone(timedelta(hours=9))


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    ap.add_argument("--stale-days", type=int, default=14)
    ap.add_argument("--max", type=int, default=7)
    a = ap.parse_args()
    today = parse_date(a.today) or datetime.now(KST).date()

    tasks = json.load(sys.stdin)
    out = []
    for t in tasks:
        due = parse_date(t.get("기한"))
        mention = parse_date(t.get("최근 언급일"))
        d_due = (due - today).days if due else None
        d_mention = (today - mention).days if mention else None
        flags, score = [], 0
        if d_due is not None:
            if d_due < 0:
                flags.append("기한 경과"); score += 100 + min(-d_due, 30)
            elif d_due <= 2:
                flags.append("기한 임박"); score += 60 - d_due * 10
            else:
                score += max(0, 20 - d_due)
        if d_mention is not None and d_mention > a.stale_days:
            flags.append("방치"); score += 30 + min(d_mention - a.stale_days, 30)
        if t.get("구분") == "명시":
            score += 15
        if t.get("상태") == "진행":
            score += 10
        if t.get("상태") == "보류":
            score -= 20
        out.append({**t, "days_to_due": d_due, "days_since_mention": d_mention,
                    "flags": flags, "score": score})

    ranked = sorted(out, key=lambda x: (-x["score"], x.get("구분") != "명시"))
    candidates = [x for x in ranked if x.get("상태") != "보류"][: a.max]
    stale = [x for x in out if "방치" in x["flags"]]
    json.dump({"today": today.isoformat(), "tasks": out,
               "today_candidates": candidates, "stale": stale},
              sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
