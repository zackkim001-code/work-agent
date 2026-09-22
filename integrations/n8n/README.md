# n8n approval-relay (Phase 4 — 보류)

17:00 텔레그램 확인 발송과 버튼·답장 콜백 처리. 수집(inbox-harvest)이 M365 커넥터 차단으로 보류 중이라 **아직 만들지 않는다.** 대기함에 들어올 항목이 없으면 보낼 것도 없다.

차단이 풀렸을 때의 구성 (설계서 2.4 B4~B6):

## 워크플로 1: 17:00 발송

```
Schedule (월~금 17:00 Asia/Seoul)
  → Notion: Get Many (업무 로그 DB, 필터 상태 = 확인대기, 정렬 생성 시각 오름차순, 최대 10)
  → Notion: Get Many (상태 = 장기대기, 건수만)
  → Notion: Get Page (운영 기준, harvest_failed)
  → Telegram: Send Message (헤더: 총 건수 · 장기대기 건수 · 수집 실패 플래그)
  → Loop over items
      → Telegram: Send Message (프로젝트 › 스레드 / 요약 / 출처·발신자 / 대기일수 / 노션 링크
                                inline keyboard: [반영 ok:<page_id>] [제외 no:<page_id>] [수정 edit:<page_id>])
      → Notion: Update Page (텔레그램 메시지 ID = message_id, 대기일수 += 1)
```

금액·단가·계약 조건은 메시지에 넣지 않는다 (요약 필드만 사용, 원문 발췌는 보내지 않음).

## 워크플로 2: 콜백·답장 처리

```
Telegram Trigger (callback_query + message)
  → IF chat.id ∉ 허용 목록 → 아무것도 하지 않고 종료
  → Switch
      callback ok:<id>   → Notion Update (상태=확정)   → Telegram Edit Message ("✅ 반영")
      callback no:<id>   → Notion Update (상태=제외)   → Telegram Edit Message ("🚫 제외")
      callback edit:<id> → Notion Update (상태=수정요청, 메모 대기=true) → Edit Message ("✏️ 이 메시지에 답장으로 메모를 남겨주세요")
      message with reply_to_message
                         → Notion Get Many (텔레그램 메시지 ID = reply_to_message.message_id)
                         → 있으면 Update (수정 메모=text, 메모 대기=false) → Edit Message ("✏️ 메모 저장")
                         → 없으면 Telegram Send ("어느 항목인지 알 수 없습니다. 해당 메시지에 답장해주세요")
  → 실패 시 2회 재시도, 그래도 실패면 Telegram Send ("반영 실패, 다시 눌러주세요")
```

수정 메모 적용과 현황 요약 갱신은 LLM 판단이 필요하므로 n8n이 하지 않고 다음 05:00 brief-prep C0가 한다.

## 필요한 자격증명

- Notion 통합 토큰 (업무 에이전트 페이지에 통합 연결)
- Telegram Bot 토큰, 본인 chat_id (허용 목록)

export JSON(`approval-relay.json`)은 실제로 만들어 테스트한 뒤 여기에 둔다.
