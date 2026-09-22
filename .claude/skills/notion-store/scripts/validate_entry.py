#!/usr/bin/env python3
"""노션 기록 전 항목 검증 + 기록 후 건수 대조.

사용법:
  # 쓰기 전: stdin으로 항목 배열(JSON)을 넣으면 스키마를 검사한다.
  python validate_entry.py --kind log  < entries.json
  python validate_entry.py --kind task < tasks.json

  # 쓰기 후: 요청 배열과 노션이 돌려준 결과 배열을 대조한다.
  python validate_entry.py --check --requested entries.json --returned result.json

종료 코드: 0 통과 / 1 검증 실패 (stderr에 사유) / 2 사용법 오류

entry_id 생성:
  python validate_entry.py --make-id --session <세션ID> --seq <순번>
  python validate_entry.py --make-id --source-ref <메시지ID>

송출 검사 (노션 밖으로 나가는 문안: 카카오톡 본문, 낭독 대본, 향후 텔레그램):
  python validate_entry.py --outbound --max 200 --max-urls 1 < message.txt   # 카카오톡 본문
  python validate_entry.py --outbound --max 1200 --max-urls 0 < script.txt   # 낭독 대본
  검사: 글자 수, URL 개수, 금칙 패턴(금액·비율·단가/계약 수치·전화·계좌·이메일).
  종료 코드 0 통과 / 1 위반 (stderr에 패턴명과 해당 문구)
"""
import argparse
import hashlib
import json
import re
import sys

# Windows 기본 인코딩(cp949)에서 한국어 키가 깨지므로 UTF-8로 고정
for _s in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

LOG_TYPES = {"진행", "결정", "이슈", "요청", "메모"}
LOG_SOURCES = {"직접입력", "Outlook", "Teams"}
LOG_STATUS = {"확정", "확인대기", "장기대기", "제외", "수정요청"}
JUDGEMENTS = {"신규", "중복", "상충"}
TASK_ORIGIN = {"명시", "추정"}
TASK_STATUS = {"열림", "진행", "보류", "완료", "기각", "확인대기", "제외"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 송출 규칙 (설계 8.4): 노션 밖으로 나가는 문안에 있으면 안 되는 것
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
OUTBOUND_PATTERNS = [
    # 한국어 단위 뒤에는 조사가 붙는다("1,500원으로") — 단어 경계를 요구하지 않는다. 로마자 단위만 \b.
    ("금액", re.compile(r"[₩$€¥]\s?\d|\d[\d,\.]*\s?(원|만원|천원|백만원|억|달러)|\d[\d,\.]*\s?(USD|KRW|EUR|JPY)\b")),
    ("비율", re.compile(r"\d+(\.\d+)?\s?(%|퍼센트|프로\b)")),
    ("단가·계약 수치", re.compile(r"(단가|금액|계약금|인상률|인상폭|납품가|견적가|총액|예산|할인율)\s*[:：은는이가을를]?\s*\d")),
    ("전화번호", re.compile(r"01[016789]-?\d{3,4}-?\d{4}|\b0\d{1,2}-\d{3,4}-\d{4}\b")),
    ("계좌번호", re.compile(r"(?!\d{4}-\d{2}-\d{2}\b)\b\d{2,6}-\d{2,6}-\d{2,8}(-\d+)?\b")),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
]


def check_outbound(text, max_len=200, max_urls=1):
    """송출 문안 검사. 위반 목록을 돌려준다 (비어 있으면 통과)."""
    errs = []
    text = text or ""
    n = len(text.strip())
    if n == 0:
        errs.append("문안이 비어 있음")
    if n > max_len:
        errs.append(f"길이 초과: {n}자 > {max_len}자")
    urls = URL_RE.findall(text)
    if len(urls) > max_urls:
        errs.append(f"URL {len(urls)}개 > 허용 {max_urls}개")
    # URL 자체의 숫자·하이픈이 계좌·전화로 오검출되지 않게 URL은 빼고 검사한다
    body = URL_RE.sub(" ", text)
    for name, rx in OUTBOUND_PATTERNS:
        for m in rx.finditer(body):
            s0 = max(0, m.start() - 8)
            errs.append(f"금칙 패턴 [{name}]: …{body[s0:m.end() + 8].strip()}…")
    return errs


def make_id(session=None, seq=None, source_ref=None):
    if source_ref:
        raw = f"src:{source_ref}"
    elif session is not None and seq is not None:
        raw = f"sess:{session}:{seq}"
    else:
        raise ValueError("session+seq 또는 source_ref 필요")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _req(d, key, errs, prefix):
    if key not in d or d[key] in (None, "", []):
        errs.append(f"{prefix}: '{key}' 누락")
        return None
    return d[key]


def validate_log(e, i):
    errs = []
    p = f"log[{i}]"
    _req(e, "entry_id", errs, p)
    _req(e, "요약", errs, p)
    d = _req(e, "날짜", errs, p)
    if d and not DATE_RE.match(str(d)):
        errs.append(f"{p}: '날짜' 형식 YYYY-MM-DD 아님: {d}")
    _req(e, "프로젝트", errs, p)  # 페이지 ID 또는 이름 ("미분류" 허용)
    t = _req(e, "유형", errs, p)
    if t and t not in LOG_TYPES:
        errs.append(f"{p}: '유형' 값 오류: {t}")
    s = _req(e, "출처", errs, p)
    if s and s not in LOG_SOURCES:
        errs.append(f"{p}: '출처' 값 오류: {s}")
    st = _req(e, "상태", errs, p)
    if st and st not in LOG_STATUS:
        errs.append(f"{p}: '상태' 값 오류: {st}")
    if s == "직접입력" and st not in (None, "확정"):
        errs.append(f"{p}: 직접입력은 상태가 '확정'이어야 함")
    if s in ("Outlook", "Teams"):
        if st not in (None, "확인대기"):
            errs.append(f"{p}: 수집분은 상태가 '확인대기'여야 함")
        if not e.get("출처 참조"):
            errs.append(f"{p}: 수집분은 '출처 참조'(메시지 ID) 필수")
    j = e.get("판정")
    if j and j not in JUDGEMENTS:
        errs.append(f"{p}: '판정' 값 오류: {j}")
    if j == "상충" and not e.get("상충 대상"):
        errs.append(f"{p}: 판정이 '상충'이면 '상충 대상' 필수")
    if not e.get("원문 발췌"):
        errs.append(f"{p}: '원문 발췌' 누락 (재분류용, 필수)")
    return errs


def validate_task(t, i):
    errs = []
    p = f"task[{i}]"
    _req(t, "제목", errs, p)
    _req(t, "프로젝트", errs, p)
    o = _req(t, "구분", errs, p)
    if o and o not in TASK_ORIGIN:
        errs.append(f"{p}: '구분' 값 오류: {o}")
    if o == "추정" and not t.get("추정 근거"):
        errs.append(f"{p}: 추정 할 일은 '추정 근거' 필수")
    st = _req(t, "상태", errs, p)
    if st and st not in TASK_STATUS:
        errs.append(f"{p}: '상태' 값 오류: {st}")
    if st == "확인대기" and not t.get("출처 로그"):
        errs.append(f"{p}: 확인대기 후보는 '출처 로그' 필수")
    d = t.get("기한")
    if d and not DATE_RE.match(str(d)):
        errs.append(f"{p}: '기한' 형식 YYYY-MM-DD 아님: {d}")
    return errs


def check(requested, returned):
    """요청 건수와 반환 건수, entry_id 대조."""
    errs = []
    if len(requested) != len(returned):
        errs.append(f"건수 불일치: 요청 {len(requested)} / 생성 {len(returned)}")
    ret_ids = {r.get("entry_id") for r in returned if r.get("entry_id")}
    for r in returned:
        if not (r.get("id") or r.get("url")):
            errs.append(f"반환 항목에 페이지 ID/URL 없음: {r}")
    if ret_ids:
        missing = [e["entry_id"] for e in requested if e.get("entry_id") not in ret_ids]
        if missing:
            errs.append(f"생성되지 않은 entry_id: {missing}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["log", "task"])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--requested")
    ap.add_argument("--returned")
    ap.add_argument("--make-id", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--seq", type=int)
    ap.add_argument("--source-ref")
    ap.add_argument("--outbound", action="store_true", help="송출 문안 검사 (stdin 텍스트)")
    ap.add_argument("--max", type=int, default=200, help="--outbound 최대 글자 수")
    ap.add_argument("--max-urls", type=int, default=1, help="--outbound 허용 URL 개수")
    a = ap.parse_args()

    if a.make_id:
        print(make_id(a.session, a.seq, a.source_ref))
        return 0

    if a.outbound:
        text = sys.stdin.read()
        errs = check_outbound(text, a.max, a.max_urls)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        print(f"OK: {len(text.strip())}자, URL {len(URL_RE.findall(text))}개")
        return 0

    if a.check:
        if not (a.requested and a.returned):
            print("--check에는 --requested, --returned 필요", file=sys.stderr)
            return 2
        with open(a.requested, encoding="utf-8") as f:
            req = json.load(f)
        with open(a.returned, encoding="utf-8") as f:
            ret = json.load(f)
        errs = check(req, ret)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        print(f"OK: {len(req)}건 대조 완료")
        return 0

    if not a.kind:
        print("--kind 필요", file=sys.stderr)
        return 2
    data = json.load(sys.stdin)
    if isinstance(data, dict):
        data = [data]
    fn = validate_log if a.kind == "log" else validate_task
    errs = []
    for i, item in enumerate(data):
        errs.extend(fn(item, i))
    ids = [d.get("entry_id") for d in data if d.get("entry_id")]
    if len(ids) != len(set(ids)):
        errs.append("entry_id 중복")
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    print(f"OK: {len(data)}건 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
