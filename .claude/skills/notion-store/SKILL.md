---
name: notion-store
description: 업무 에이전트의 노션 저장소 읽기·쓰기 규칙. 프로젝트/업무 로그/할 일/브리핑 DB와 운영 기준 페이지에 접근하기 직전에 반드시 참조한다. 다른 스킬(work-intake, status-report, brief-prep, brief-deliver, weekly-report, inbox-harvest)이 노션을 만질 때 이 규칙을 따른다.
---

# notion-store

노션이 유일한 저장소다. 로컬 파일에 운영 상태를 두지 않는다. 모든 ID는 `references/notion_schema.json`에서 가져온다 — 검색으로 DB를 찾지 않는다.

## ID 표 (요약)

| 대상 | data_source / page ID |
|---|---|
| 프로젝트 DB | `collection://530dbf9f-134c-4c6c-928e-c53e6c1bea99` |
| 업무 로그 DB | `collection://78533066-70f3-48ed-911a-556a75f09f83` |
| 할 일 DB | `collection://dd44023a-a0d3-4ee6-8434-275771fa471b` |
| 브리핑 DB | `collection://e21a4df3-462f-45ac-8516-5ac920b7a7ec` |
| 운영 기준 페이지 | `3df9b92a-6770-8124-b065-f27031bace5f` |
| 주간보고 모음 페이지 | `3df9b92a-6770-8162-934e-d47f5c902a37` |
| 프로젝트: 미분류 | `3df9b92a-6770-817f-9799-e03f9e2fc15c` |

## 읽기

- 기본은 `query-data-sources`의 **rows 모드** + 구조화 필터. 이 플랜에서 SQL 모드는 사용량 제한이 있고 다중 DB 조인은 불가하다.
- 자주 쓰는 조회:
  - 프로젝트 목록: projects 전체 (4~10건)
  - 스레드의 최근 30일 확정 로그: logs, `프로젝트 relation_contains <id>` AND `상태 enum_is 확정` AND `날짜 date_is_after <30일 전>`, 스레드는 결과에서 텍스트 비교
  - 열린 할 일: tasks, `상태 enum_is [열림, 진행, 보류]`
  - 대기함: logs, `상태 enum_is 확인대기` 정렬 `생성 시각 ascending`
  - 열린 상충: logs, `판정 enum_is 상충` AND `상충 해소 기록 is_empty`
- 관계(relation) 속성은 rows 모드에서 페이지 URL 배열로 온다. 프로젝트 이름은 `notion_schema.json`의 seed 표로 역매핑한다.
- 페이지 본문(운영 기준, 브리핑, 주간보고)은 `fetch`로 읽는다.

## 쓰기

- 쓰기는 **LLM이 노션 커넥터 도구로 직접** 한다 (스크립트는 커넥터를 호출할 수 없다).
- 순서: (1) 항목 배열을 JSON으로 만든다 → (2) `scripts/validate_entry.py --kind log|task`로 검증 → (3) `entry_id`로 기존 항목 조회, 있으면 건너뜀 → (4) `create-pages`로 생성 (한 번에 최대 100건) → (5) 반환된 ID를 모아 `validate_entry.py --check`로 건수 대조.
- 속성 형식:
  - 날짜: `"date:날짜:start": "2026-09-18"`, `"date:날짜:is_datetime": 0`
  - 체크박스: `"__YES__"` / `"__NO__"`
  - 관계: 페이지 URL 또는 ID 배열 `["3df9b92a-..."]`
  - 셀렉트: 옵션 이름 문자열 그대로. 스키마에 없는 옵션을 만들지 않는다.
- 갱신은 `update-page` `update_properties`. 생략한 속성은 그대로 남는다.
- 프로젝트 `현재 상황`은 덮어쓴다 (이력은 로그에 있다). `현황 갱신일`을 같이 갱신한다.
- 새 스레드: 프로젝트 페이지의 `스레드` 텍스트 끝에 한 줄 추가한다. 기존 줄은 건드리지 않는다.
- 운영 기준 페이지는 `update-page` `update_content`로 해당 표의 셀만 바꾼다. 페이지 전체를 교체하지 않는다.
- 브리핑 페이지 `전달 기록` 섹션은 `update-page` `update_content`로 끝에 한 줄만 추가한다 (brief-deliver 전용). 다른 섹션은 건드리지 않는다.
- 노션 밖으로 나가는 문안(카카오톡 본문, 듣기 페이지 대본, 향후 텔레그램)은 보내기 전에 `scripts/validate_entry.py --outbound`로 검사한다 (설계 8.4 송출 규칙: 금액·단가·비율·계약 수치·연락처 금지, 글자 수·URL 개수 제한).

## entry_id

- 직접 입력: `validate_entry.py --make-id --session <세션ID> --seq <순번>` (세션ID는 대화 시작 시각 ISO 문자열이면 충분)
- 수집: `--make-id --source-ref <메시지 ID>`
- 재시도 전에 반드시 `entry_id string_is <값>`으로 존재 여부를 확인한다. 부분 성공 후 재시도로 중복이 생기는 것을 막는 유일한 장치다.

## 실패 처리

- 생성·갱신 실패: 2회 재시도 (재시도 전 entry_id 조회). 그래도 실패하면 대화형 세션에서는 "노션 기록 실패 N건"과 원문을 보여주고 지시를 받는다. 예약 작업에서는 브리핑 페이지나 운영 기준 `harvest_note`에 실패 사실을 적는다.
- 조회 실패: 1회 재시도. 실패하면 "조회 실패"를 명시하고 추정으로 메우지 않는다.

## 금지

- 확인대기·장기대기·수정요청 상태의 로그를 확정 사실처럼 인용하지 않는다. 건수만 말한다.
- 스키마 밖의 속성이나 옵션을 만들지 않는다. 구조 변경이 필요하면 사용자에게 말하고 `notion_schema.json`을 함께 고친다.
- 페이지를 삭제하지 않는다. 제외는 상태 변경으로만 한다.
