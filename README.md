# work-agent

구매기획팀 업무 기록·브리핑 에이전트. 노션을 저장소로 쓰고, 평일 아침 브리핑을 카카오톡과 듣기 페이지로 전달한다.

- 설계: [docs/design.md](docs/design.md)
- 운영 개시 절차: [docs/setup-checklist.md](docs/setup-checklist.md)
- 대화형 세션 지침: [CLAUDE.md](CLAUDE.md)
- 스킬: `.claude/skills/` (brief-prep, brief-deliver, notion-store, work-intake, status-report, weekly-report, org-reference, inbox-harvest)
- 예약 실행 프롬프트: `scheduled-tasks/` (05:00 브리핑, 06:00 전달, 16:30 수집은 보류)

이 저장소는 claude.ai 루틴(클라우드 예약 실행)이 매일 클론해서 쓴다. 루틴 세션은 저장소 루트를 작업 폴더로 삼으므로 `.claude/skills/`의 스킬이 프로젝트 스킬로 바로 잡힌다. 회사 내부 문서(`org-reference/references/`)는 커밋하지 않는다.
