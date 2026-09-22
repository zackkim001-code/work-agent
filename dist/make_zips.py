#!/usr/bin/env python3
"""스킬 폴더 → 업로드용 zip. 항목 경로를 슬래시(/)로 쓴다.

PowerShell Compress-Archive 는 항목 이름에 백슬래시를 넣어 claude.ai 스킬 업로드가
"Zip file contains path with invalid characters" 로 거부한다 (2026-09-22 확인). 반드시 이 스크립트로 만든다.

사용법: python make_zips.py            # 다섯 스킬 모두
        python make_zips.py brief-prep # 하나만
"""
import io
import os
import sys
import zipfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.join(os.path.dirname(HERE), ".claude", "skills")
ALL = ["brief-deliver", "brief-prep", "notion-store", "weekly-report", "work-intake"]
SKIP_DIRS = {"__pycache__", ".git"}
SKIP_EXT = {".pyc"}


def build(name):
    src = os.path.join(SKILLS, name)
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        raise SystemExit(f"{name}: SKILL.md 없음 ({src})")
    out = os.path.join(HERE, f"{name}.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for f in sorted(files):
                if os.path.splitext(f)[1] in SKIP_EXT:
                    continue
                full = os.path.join(root, f)
                arc = os.path.relpath(full, os.path.dirname(src)).replace(os.sep, "/")
                z.write(full, arc)
                n += 1
    with zipfile.ZipFile(out) as z:
        bad = [i.filename for i in z.infolist() if "\\" in i.filename]
        names = [i.filename for i in z.infolist()]
    if bad:
        raise SystemExit(f"{name}: 백슬래시 경로 남음 {bad}")
    print(f"{name}.zip: {n}개 파일, {os.path.getsize(out)}바이트")
    for nm in names:
        print("   ", nm)


if __name__ == "__main__":
    targets = sys.argv[1:] or ALL
    for t in targets:
        build(t)
