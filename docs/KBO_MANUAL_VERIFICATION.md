# KBO 수동 표본 검증 양식 (설계)

목적: KBO 공식 사이트 자동 수집이 금지된 동안, **사람이 직접 열람**한 KBO 공식 기록으로만 `kbo_verified` 를 만든다.
자동 요청·스크린샷 자동화는 쓰지 않는다. 양식: `docs/templates/kbo_manual_check.csv`.

## 1. 한 줄 = 한 경기·한 선수·한 항목

| 열 | 필수 | 내용 |
| --- | --- | --- |
| `check_id` | ✓ | 확인자가 붙이는 고유 번호(예 `2025-0001`) |
| `season` · `game_id` | ✓ | KBO GameId 13자(예 `20250719HHKT0`) |
| `role` · `player_id` · `player` | ✓ | `pitcher`/`batter`, KBO playerId, 이름 |
| `metric` | ✓ | `outs`·`bf`·`h`·`bb`·`hbp`·`so`·`r`·`er` / `ab`·`h`·`hr`·`bb`·`so` (API 항목명과 같다) |
| `kbo_value` | ✓ | KBO 게임센터 화면에 보이는 값 그대로. 이닝은 화면 표기(`5 2/3`)를 함께 `kbo_display` 에 적고 `kbo_value` 는 아웃 수 |
| `kbo_display` |  | 화면 표기 원문 |
| `kbo_page` | ✓ | 열람한 화면(예: 게임센터 > 리뷰 > 박스스코어). URL 을 적되 자동 재방문하지 않는다 |
| `viewed_at` | ✓ | 열람 시각(KST, ISO 8601) |
| `checker` | ✓ | 확인자(역할 또는 이니셜) |
| `evidence` |  | 화면 캡처 파일명 — 저장소에 올리지 않고 로컬 보관(저작권) |
| `note` |  | 정정 공지·특이사항 |

## 2. 적재·판정 규칙(P2 이후 구현)

- 테이블 `verify.kbo_manual_check`(불변 추가). 같은 항목을 다시 확인하면 새 줄 — 최신 `viewed_at` 이 현재값.
- 판정은 따로 계산한다(값을 고치지 않는다):
  - `kbo_verified`: KBO 값 == 네이버 박스스코어 값 (외부 기록이 KBO 로 확인됨)
  - `kbo_conflict`: 다름 — 네이버 값의 신뢰 문제로 기록, 화면에 노출
  - 자체 계산값과의 일치는 별도 상태(`observed_kbo_match` 등)로만 표시
- 확인하지 않은 항목은 `not_checked`. 표본 결과를 다른 경기·선수로 일반화하지 않는다.

## 3. 우선 표본(2025)

| 묶음 | 경기 수 | 이유 |
| --- | --- | --- |
| `called_game` | 7 | 이닝 도중 종료 — 아웃 수 정의가 갈린다 |
| `tie` | 22 | 연장·무승부 처리 |
| `walkoff` | 37 | 마지막 반이닝 아웃 미입증 |
| 관측 충돌 3건 경기(20250612SKLG0 · 20250816HHNC0) | 2 | 원본 투수 표기·귀속 확인 |
| 무작위 일반 경기 | 20 | 기준선 |
