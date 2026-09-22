#!/usr/bin/env python3
"""낭독 대본 → mp3 (Microsoft Edge 신경망 음성, edge-tts 패키지). API 키가 필요 없다.

edge-tts는 Edge 브라우저의 '소리 내어 읽기'가 쓰는 온라인 음성 서비스를 그대로 호출한다.
공식 API가 아니므로 언젠가 막힐 수 있다. 그래서 이 스크립트가 실패해도 듣기 페이지는
기기 음성(브라우저 TTS)만으로 만들어지도록 brief-deliver 절차에 예비 경로를 둔다.

사용법:
  python make_audio.py --script-file script.txt --out-dir . \
      [--lang ko|en] [--voices ko-KR-SunHiNeural,ko-KR-InJoonNeural] [--rate +0%] [--timeout 90]
  --lang ko 기본 = 선히·인준 (brief-sunhi.mp3, brief-injoon.mp3)
  --lang en 기본 = Jenny·Guy (brief-jenny.mp3, brief-guy.mp3) — 영어 낭독 대본용

출력 (stdout JSON):
  {"files": [{"voice": "ko-KR-SunHiNeural", "label": "선히 (여성)", "path": "…/brief-sunhi.mp3", "bytes": 348048}],
   "failed": [{"voice": "…", "error": "…"}]}
종료 코드: 0 하나 이상 성공 / 1 전부 실패 / 2 사용법 오류

edge_tts 모듈이 없으면 `pip install --target <out-dir>/pylib edge-tts`로 설치를 시도한다
(원격 예약 작업 샌드박스에는 미리 깔려 있지 않다).
"""
import argparse
import json
import os
import subprocess
import sys

for _s in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

VOICE_LABELS = {
    "ko-KR-SunHiNeural": ("선히 (여성)", "sunhi"),
    "ko-KR-InJoonNeural": ("인준 (남성)", "injoon"),
    "ko-KR-HyunsuMultilingualNeural": ("현수 (남성)", "hyunsu"),
    "en-US-JennyNeural": ("Jenny (female)", "jenny"),
    "en-US-GuyNeural": ("Guy (male)", "guy"),
    "en-US-AriaNeural": ("Aria (female)", "aria"),
    "en-GB-SoniaNeural": ("Sonia (British)", "sonia"),
}
DEFAULT_VOICES = {
    "ko": "ko-KR-SunHiNeural,ko-KR-InJoonNeural",
    "en": "en-US-JennyNeural,en-US-GuyNeural",
}


def ensure_edge_tts(out_dir, env):
    """edge_tts 를 import 할 수 있게 한다. 없으면 out_dir/pylib 에 설치한다."""
    probe = subprocess.run([sys.executable, "-c", "import edge_tts"], env=env, capture_output=True)
    if probe.returncode == 0:
        return True, ""
    pylib = os.path.join(out_dir, "pylib")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", pylib, "edge-tts"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return False, f"pip 설치 실패: {(r.stderr or r.stdout).strip()[-400:]}"
    env["PYTHONPATH"] = pylib + os.pathsep + env.get("PYTHONPATH", "")
    probe = subprocess.run([sys.executable, "-c", "import edge_tts"], env=env, capture_output=True)
    return probe.returncode == 0, "" if probe.returncode == 0 else "설치 후에도 import 실패"


def synth(voice, script_file, out_path, rate, timeout, env):
    cmd = [sys.executable, "-m", "edge_tts", "--voice", voice, "--file", script_file,
           "--write-media", out_path, "--rate", rate]
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"{timeout}초 초과"
    if r.returncode != 0:
        return (r.stderr or r.stdout).strip()[-400:] or f"종료 코드 {r.returncode}"
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        return "출력 파일이 비어 있음"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script-file", required=True)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--lang", choices=["ko", "en"], default="ko",
                    help="기본 목소리 묶음: ko = 선히·인준, en = Jenny·Guy (--voices 를 주면 무시)")
    ap.add_argument("--voices", default=None, help="edge-tts 목소리 이름을 쉼표로. 생략하면 --lang 기본값")
    ap.add_argument("--rate", default="+0%", help="edge-tts 속도 (예: -5%%, +0%%, +10%%). 재생 속도는 페이지에서 따로 조절한다")
    ap.add_argument("--timeout", type=int, default=90, help="목소리 하나당 최대 초")
    a = ap.parse_args()

    if not os.path.isfile(a.script_file):
        print(f"대본 파일 없음: {a.script_file}", file=sys.stderr)
        return 2
    os.makedirs(a.out_dir, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    pylib = os.path.join(a.out_dir, "pylib")
    if os.path.isdir(pylib):
        env["PYTHONPATH"] = pylib + os.pathsep + env.get("PYTHONPATH", "")

    ok, why = ensure_edge_tts(a.out_dir, env)
    result = {"files": [], "failed": []}
    if not ok:
        result["failed"].append({"voice": "*", "error": why})
        print(json.dumps(result, ensure_ascii=False))
        return 1

    voices = a.voices or DEFAULT_VOICES[a.lang]
    for voice in [v.strip() for v in voices.split(",") if v.strip()]:
        label, slug = VOICE_LABELS.get(voice, (voice, voice.lower().replace("-", "_")))
        out_path = os.path.abspath(os.path.join(a.out_dir, f"brief-{slug}.mp3"))
        err = synth(voice, a.script_file, out_path, a.rate, a.timeout, env)
        if err:
            result["failed"].append({"voice": voice, "error": err})
        else:
            result["files"].append({"voice": voice, "label": label, "path": out_path,
                                    "bytes": os.path.getsize(out_path)})
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["files"] else 1


if __name__ == "__main__":
    sys.exit(main())
