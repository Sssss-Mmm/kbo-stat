# P3-A 설계 보고서 — 타자 고급 지표 (ISO · BABIP · BB% · K%)

작성: 2026-10-25 · 기준: `main` `3179809` · 1~5장 = 조사·설계, 6~7장 = 백엔드 1단계 구현 결과(계산·출처 판정·선수 연결·테스트).
분석은 로컬 수집 자료(`data/`, 읽기만)와 운영 DB 읽기 전용 조회로 했다. 데이터 이용 권한 확인 전이라 결과는 비공개 화면에만 쓴다.

## 0. 결론 요약

| 지표 | 실제 데이터로 계산 가능한 범위 | 계산 불가(이유) |
| --- | --- | --- |
| **ISO** | **전 범위.** 네이버 시즌 기록 2007–2026 전체 타자(선수 ID), KBO 기록실 1982–2026 규정 이상, 2025 투구 계산 | — |
| **BABIP** | **2025 시즌, 투구 계산이 모든 경기에서 완결된 타자만**(118/299명) — SF 가 있는 유일한 자료 | 그 밖 전부: 네이버·KBO 기록실 자료에 **SF(희생플라이) 열이 없다.** 네이버가 준 BABIP 값은 있으나 우리가 재현할 수 없다 → '출처 값'으로만 표시 |
| **BB%** | **KBO 기록실 규정 이상 타자 1982–2026**(PA 있음, ID 연결은 2008–2026 의 94%) + **2025 완결 타자**(네이버 AB·BB·HBP + 투구 계산 SF·SH 로 PA 조립) | 규정 미달 타자 2007–2024·2026: **PA 가 어디에도 없다**(네이버 자료에 PA·SF·SH 없음) |
| **K%** | BB% 와 같음 | BB% 와 같음 |

추정·근사로 채우지 않는다. 계산할 수 없는 칸은 `null` + 사유(화면 '자료 없음'), 출처가 준 값은 계산값과 분리해 '출처 값'으로 표시한다.

## 1. 현재 구조

### 1.1 타자 기록 자료(저장 단위·범위)

| 자료 | 저장 위치 | 단위 | 범위 | 선수 ID |
| --- | --- | --- | --- | --- |
| A. KBO 기록실 시즌 타자 | `data/raw/kbo_official/kbo_{시즌}.csv` → v1 `public.hitters`(ORM `Hitter`) | 선수×시즌, **규정 타석 이상만**(시즌당 30–62명) | 1982–2026(45시즌, DB 1,926행) | **없음**(이름·팀) |
| B. 네이버 시즌 기록 | `data/processed/kbo_naver_hitters_{시즌}.csv`(v1 `/api/player-stats`, P2-D `team_player_service`) | 선수×시즌, 출전 전원(시즌당 216–398명, AB>0 200–299명) | 2007–2026 | 있음 |
| C. 네이버 박스스코어 | v2 `official.game_batter_line`(ORM `GameBatterLine`) | 선수×경기 | 2025 | 있음 |
| D. 투구 데이터 계산 | v2 `derived.player_game`(ORM `PlayerGame`, `build_player_games.py`) | 선수×경기 + 완결 플래그(`pa_complete`, `stats_complete`) | 2025 | 있음 |
| (참고) KBO 지표 가공 | `kbo_hitter_metrics_{시즌}.csv` → v1 `hitter_metrics` | 규정 이상, PA·AVG·OBP·SLG… | 시즌별 | 없음 |

API·서비스: v1 `routers/player_stats.py`(B 를 그대로), `routers/players.py`·`services/player_service.py`(A), v2 `routers/v2.py` + `services/v2_service.py`(C·D, 2025 선수 시즌·경기·리더보드) · `services/team_player_service.py`(B, 팀 상세·검색·프로필).

### 1.2 필드 존재·완전성

| 필드 | A. KBO 기록실 | B. 네이버 시즌 | C. 박스스코어 | D. 투구 계산(2025) |
| --- | --- | --- | --- | --- |
| PA | ✓ | **✗** | ✗ | ✓(자동 고의4구 빠짐 → 공식보다 1–7 작음) |
| AB · H · HR · SO · BB | ✓ | ✓ | ✓ | ✓(BB 는 자동 고의4구 빠짐) |
| 2B · 3B | ✓ | ✓ | ✗ | ✓ |
| HBP | ✓ | ✓ | ✗ | ✓ |
| **SF** | **✗** | **✗** | ✗ | ✓ |
| SH | ✗ | ✗ | ✗ | ✓ |
| AVG | ✓ | ✓ | — | 계산 |
| SLG | ✗(ISOP 는 있음, 2B·3B 로 계산 가능) | ✓ | — | 계산 |
| 출처가 준 ISO · BABIP | ISOP | ISO · BABIP | — | — |

결측: A·B 필수 열 결측 0(전 시즌). D: 타자-경기 16,459행 중 `pa_complete` 99.9%, `stats_complete` 96.9% — **시즌 전 경기가 완결된 타자는 299명 중 118명**, 나머지 181명은 미완결 경기 1–18개(합계가 하한값).

### 1.3 교차 검증으로 확인한 것

| 확인 | 결과 | 뜻 |
| --- | --- | --- |
| 네이버 ISO vs SLG − AVG | 전 시즌 차이 ≤ 0.0005(반올림) | ISO 는 개수로 계산해도 출처와 같다 |
| 네이버 BABIP vs (H−HR)/(AB−SO−HR) (SF=0) | 시즌마다 약 50% 가 계산값이 더 큼 | 네이버는 분모에 SF 를 넣는다 — SF 없이 재현 불가 |
| **D 의 SF 로 계산한 BABIP vs 네이버 BABIP(2025 완결 115명)** | **100% 가 0.001 이내** | 공식(SF 포함)이 출처와 같다 — D 로 정확히 계산 가능 |
| D 시즌 합계 vs 네이버(2025, 완결 선수) | AB·H·HR·SO·HBP 100% 일치, BB 86.4% | 자동 고의4구는 투구가 없어 D 에 안 잡힌다 — **D 의 BB·PA 를 그대로 쓰면 안 된다** |
| D 의 PA vs KBO 기록실 PA(2025 규정 이상 42명) | 38.1% 일치(차이 −1~−16) | D 의 PA 는 하한값 |
| **PA 조립 = 네이버 AB+BB+HBP + D 의 SF+SH** vs KBO PA | 88.1% 일치, **완결 선수 100%**, 나머지는 −1(미완결 경기의 희생타 누락) | 완결 선수는 PA 를 정확히 조립할 수 있다 |
| KBO 기록실 ↔ 네이버 ID 연결(이름·팀·AB·H, 2007–2026) | 979명 중 **94.1% 1:1**, 모호 0, 미연결 58(2007 전원·2008–09 일부: 네이버 팀명 빈 행, 2025 1명) · 1:1 은 BB·SO 100% 일치 | 이름·팀만으로는 동명이인이 섞인다(2025 같은 팀 동명이인 2명) — **AB·H 까지 맞춰야 한다** |

## 2. 지표 설계

공통 규칙
- 계산은 **개수에서** 한다(반올림된 비율끼리 빼지 않는다). 표시 반올림 ROUND_HALF_UP(순위표와 같은 규칙): ISO·BABIP 소수 3자리, BB%·K% 소수 1자리.
- 응답의 각 지표는 `{value, status, basis, reason}`. `status`: `calculated`(우리가 계산) · `source`(출처가 준 값, 재현 안 됨) · `unavailable`(필요한 자료 없음·불가능한 조합, 사유) · `zero_denominator`.
- 분모 0·음수 → `value: null`, `status: zero_denominator`. 입력 하나라도 없음 → `null`, `unavailable` + 빠진 입력 이름. **0 으로 채우지 않는다.**
- 시즌 단위 = 선수×시즌(네이버 기록 기준 소속 1팀). 여러 시즌 합산(통산)은 **개수를 더한 뒤** 계산 — 비율 평균 금지(P3-A 범위 밖, 구조만 열어 둠).
- 리그 백분위의 모집단은 그 시즌 규정 충족 타자 중 같은 `status` 의 값만(계산값과 출처 값을 섞지 않는다).

### 2.1 ISO = SLG − AVG = (2B + 2·3B + 3·HR) / AB

| 항목 | 내용 |
| --- | --- |
| 원본 | B(2007–2026, 전원) 우선. ID 없는 시즌(1982–2006)은 A(규정 이상, 이름만) |
| 계산 | (2B + 2·3B + 3·HR)/AB — SLG−AVG 와 같은 값을 반올림 손실 없이 |
| 분모 0 | AB = 0 → `zero_denominator`(투수 타석 0 등) |
| 누락 | 2B·3B·HR·AB 중 하나라도 없으면 `unavailable` |
| 검증 | 출처 ISO(B)·ISOP(A)와 ±0.0005 |

### 2.2 BABIP = (H − HR) / (AB − SO − HR + SF)

| 항목 | 내용 |
| --- | --- |
| 원본 | **D(2025)의 SF + 같은 시즌 네이버 H·HR·AB·SO** — 단 그 선수의 시즌 전 경기가 `stats_complete` 일 때만 |
| 계산 불가 | SF 가 없는 모든 경우(2007–2024·2026 전원, 2025 미완결 181명) → `unavailable`(사유 "SF 자료 없음" / "투구 계산 미완결 경기 N개") |
| 출처 값 | 네이버 BABIP 를 `status: source` 로 별도 필드에 — 화면에 '출처 값(네이버)'으로 표시, 계산값과 섞지 않음 |
| 분모 0 | AB−SO−HR+SF ≤ 0 → `zero_denominator` |
| 검증 | 2025 완결 115명에서 출처 값과 ±0.001(이미 100% 확인) — 회귀 테스트로 고정 |

### 2.3 BB% = BB / PA × 100 · 2.4 K% = SO / PA × 100

| 항목 | 내용 |
| --- | --- |
| PA 출처(우선순위) | ① A 의 PA(KBO 기록실, 규정 이상) — B 와 (시즌, 이름, 팀, AB, H) 가 **정확히 1명**에게만 맞을 때 ② 2025: 네이버 AB+BB+HBP + D 의 SF+SH — 그 선수의 시즌 전 경기 `stats_complete` 일 때 ③ 그 외 → `unavailable`("PA 자료 없음") |
| 분자 | BB·SO 는 B(네이버, 고의4구 포함) — A 와 100% 일치 확인. **D 의 BB 는 쓰지 않는다**(자동 고의4구 누락) |
| 분모 0 | PA = 0 → `zero_denominator` |
| 표기 | `basis`: `kbo_record_pa` / `assembled_pa_2025` — 화면 각주에 어느 PA 인지 |
| 범위 | 규정 이상 1982–2026(ID 연결 2008–2026 의 94%) + 2025 완결 타자. 규정 미달 타자는 2025 를 빼면 대부분 '자료 없음' |

## 3. API·화면

**권장: v2 에 확장, v1 은 그대로.**

| 변경 | 내용 | 호환성 |
| --- | --- | --- |
| `GET /api/v2/players/{id}/profile` 확장 | 타자 시즌 줄에 `advanced: {iso, babip, babip_source, bb_pct, k_pct}` 추가 | 필드 추가만 — 기존 키 그대로 |
| 신규 `GET /api/v2/batting/advanced?season=&team=&qualified=` | 시즌 타자 전원의 네 지표 + status·basis. 비교 화면의 리그 백분위 모집단과 리더 표에 사용 | 신규 경로 |
| v1 `/api/player-stats` | 변경 없음 | — |

화면
- **선수 비교**(`Compare.jsx`): 타자 지표에 BABIP·BB%·K% 추가(ISO 는 이미 있음). 값 옆에 status 배지(계산 / 출처 값 / 자료 없음), 백분위는 같은 status 끼리. 모집단을 v1 `/api/player-stats` → 신규 API 로.
- **선수 상세**(`PlayerV2.jsx` 시즌별 기록): 네 지표 열 + 각주(PA 출처).
- **팀 상세**(`TeamDetail.jsx` 출전 선수 표): ISO·BB%·K% 열(선택).
- 홈의 리그 BB%·K% 는 현재 PA ≈ AB+BB+HBP 근사(SF·SH 빠짐)로 계산된다 — P3-A 기준과 다르므로 같은 PR 에서 표기를 '근사'로 바꾸거나 신규 API 로 대체할지 결정 필요.

## 4. 구현 계획

| 구분 | 파일 | 내용 |
| --- | --- | --- |
| 백엔드 | `services/batting_advanced.py`(신규) | 순수 계산 함수(공식·반올림·status), PA 출처 선택, A↔B ID 연결(시즌·이름·팀·AB·H 1:1), D 시즌 합계(완결 여부) |
| | `services/team_player_service.py` | 프로필 타자 줄에 `advanced` 추가 |
| | `routers/v2.py` | 신규 경로 1개 |
| | `tests/test_batting_advanced.py`(신규) | 단위 + 실데이터 검증(`data/` 없으면 건너뜀, PG 통합은 `V2_PG_TESTS`) |
| 프론트 | `lib/p2d.js`·`lib/p2d.test.js` | 지표 정의·status 표시·백분위 모집단 규칙 |
| | `pages/Compare.jsx`, `pages/PlayerV2.jsx`, (선택) `pages/TeamDetail.jsx` | 표시 |
| DB | **스키마 변경 없음** | A 는 v1 `hitters`(이미 적재), B 는 CSV, D 는 v2 `derived.player_game` — 요청 때 계산(P2-D 와 같은 방식, 파일 수정 시각 캐시) |

단계
1. 계산 함수 + 단위 테스트(분모 0, 누락, 반올림, status) → 2. PA 출처 선택·ID 연결 + 실데이터 검증 테스트 → 3. API(프로필 확장·신규) + 회귀(v1 31·v2 19 경로 동일) → 4. 화면 → 5. 격리 환경 PG 통합·화면 검증(390·1280) → Codex 교차검증 → 후보 이미지.

테스트 전략

| 종류 | 내용 |
| --- | --- |
| 단위 | 공식별 정상값, 분모 0, 입력 누락 → null·사유, ROUND_HALF_UP 경계(.0005), 통산 합산은 개수 합 후 계산 |
| 출처 대조(실데이터, data 있을 때) | ISO = 네이버 ISO ±0.0005(2007–2026 전원) · BABIP(2025 완결) = 네이버 ±0.001 · 조립 PA = KBO PA(2025 규정 이상·완결) · A 의 BB%·K% 분자 = 네이버 |
| ID 연결 | 같은 팀 동명이인이 AB·H 로 갈리는지, 모호하면 연결 안 함 |
| 회귀 | v1/v2 기존 경로 응답 동일, 프로필 기존 키 불변 |
| 화면 | 자료 없음 칸이 0 으로 안 보이는지, status 배지, 가로 넘침 |

## 5. 위험과 검증

| 위험 | 대응 |
| --- | --- |
| 출처 혼합(네이버 개수 + 투구 계산 SF·SH)으로 만든 PA | `basis` 로 표시, 완결 선수만, KBO PA 와 100% 일치를 회귀 테스트로 고정 |
| KBO 기록실에 선수 ID 없음 | (시즌·이름·팀·AB·H) 1:1 일 때만 연결, 모호·미연결은 PA 출처로 쓰지 않음(2007·2008–09 일부 미연결) |
| 네이버 BABIP 를 계산값처럼 보이게 함 | `source` 로 분리, 백분위 모집단 분리 |
| 2025 외 시즌 규정 미달 타자 BB%·K% 대부분 공란 | 화면에 이유(PA 자료 없음) 표시 — 근사 PA 를 만들지 않는다. 범위를 넓히려면 PA·SF 를 주는 자료가 필요(새 수집 = 승인 필요) |
| 표본 작은 선수의 극단값(예 PA 3) | 값은 보이되 백분위·리더에서 제외(규정 충족 모집단) |
| 홈 리그 BB%·K% 근사와 불일치 | 3장 결정 사항 |
| 데이터 이용 권한 | 기존과 같이 비공개·localhost 만 |

추가 데이터가 있으면 계산 가능해지는 것: 시즌별 SF(→ 전 시즌 BABIP), 시즌별 PA 또는 SF+SH(→ 전원 BB%·K%). 모두 새 수집이라 이용 승인 전에는 하지 않는다.

## 6. 백엔드 1단계 구현 결과 (2026-10-25)

범위: 계산 로직 · 출처 판정 · 선수 ID 연결 · 테스트. **API·프론트·DB·운영은 바꾸지 않았다.**

| 파일 | 내용 |
| --- | --- |
| `kbo-dashboard/backend/services/batting_advanced.py`(신규) | 순수 함수 — 지표 계산 · 개수 모순 검사 · 출처 값 · KBO 기록실 ↔ 선수 ID 연결 · PA 선택 · 선수 시즌 · 리그 비율. 실데이터 검증용 읽기 전용 `load_season` |
| `kbo-dashboard/backend/tests/test_batting_advanced.py`(신규) | 합성 픽스처 20개 + 로컬 자료 읽기 전용 검증 6개(자료 없으면 건너뜀, `KBO_DATA_DIR` 로 위치 지정) |

지표 응답 형태(지표마다)

```
{"metric": "babip", "value": 0.3333…(정밀값), "display": 0.333(표시용 ROUND_HALF_UP),
 "status": "calculated|source|unavailable|zero_denominator", "reason": null|"사유",
 "provenance": {"season", "scope": "player_season|league_season", "player_id", "source", ["pa_basis"], ["note"]}}
```

- 계산은 개수에서 `Fraction` 으로 하고, `display` 만 반올림한다(ISO·BABIP 3자리, BB%·K% 1자리).
- 불가능한 조합은 계산하지 않고 `unavailable` + 사유: 음수 · 정수가 아닌 개수 · H > AB · HR > H · 2B+3B+HR > H · H+SO > AB · AB+BB+HBP > PA · BB(또는 SO) > PA.
- 선수 연결 상태: `linked` · `ambiguous`(후보 여럿, 또는 한 ID 를 기록실 여러 행이 노림) · `unmatched`(시즌 불일치·후보 없음 — 이적·팀명 누락 포함) · `team_missing` · `record_mismatch`(연결 뒤 BB·SO 불일치 → 그 PA 는 쓰지 않음).
- PA 선택: ① 검증된 KBO 기록실 PA(linked + PA ≥ AB+BB+HBP) ② 조립 PA(시즌 전 경기 완결 + 투구 계산 AB·HBP 가 시즌 기록과 같을 때) ③ `unavailable`.

실데이터 결과(로컬, 읽기 전용)

| 항목 | 결과 |
| --- | --- |
| 기록실 ↔ ID 연결 2007–2026 | 979행 중 linked 921 · unmatched 58 · ambiguous 0 · record_mismatch 0 |
| 2025 네이버 타자 398명 | ISO calculated 299 · zero_denominator 99(타수 0) |
| | BABIP calculated 115 · unavailable 280 · zero_denominator 3 — 계산값 115명 모두 출처 값과 ±0.001 |
| | BB%·K% calculated 152(PA: KBO 기록실 42 · 조립 110) · unavailable 246 |
| 조립 PA vs KBO PA | 연결된 완결 선수 전원 일치 |

구현 중 새로 확인한 것

1. **출처 ISO 는 '반올림 SLG − 반올림 AVG'** 다(2007–2026 의 5,200행 중 정확 계산과 0.0005 넘게 다른 1,012행 전부가 이것으로 설명됨, 최대 0.00098). 우리 값은 개수에서 정확히 계산하므로 표시값이 출처와 **약 20% 행(1,038행)에서 0.001 다르다.** 우리 쪽이 정확하다 — 화면에서는 출처 ISO 와 나란히 보이지 않게 하거나 차이를 각주로 밝힌다(API 단계 결정).
2. **출처 BABIP 는 분모가 0 일 수 있는 행에도 0.000 을 적는다**(2025 102행, 타수 0 인 99행 포함). 정의되지 않는 값을 0 으로 쓴 것이므로 AB−SO−HR ≤ 0 이고 출처 값이 0 이면 출처 값도 `unavailable` 로 둔다. 인플레이 타수가 있는 진짜 0 은 그대로 `source`.

## 7. 홈 화면 리그 지표 정책 (이번 단계 코드 변경 없음)

현재 홈의 리그 BB%·K% 는 PA 를 `AB + BB + HBP` 로 근사한다(SF·SH 빠짐) — **정확한 PA 기반 비율이 아니므로 '근사'로 분류**한다.

| 원칙 | 내용 |
| --- | --- |
| 계산 방식 | 리그 지표 = 분자 합계 / 분모 합계(`league_rate`). 선수별 비율의 단순 평균을 쓰지 않는다 |
| 모집단 | 그 시즌 모집단 **전원**의 PA 가 확인될 때만 리그 값을 낸다. 일부 선수(PA 확인된 선수)만으로 만든 값을 리그 전체 지표로 표시하지 않는다 — `unavailable`("PA 미확인 선수 N명") |
| 현실 | 2025 를 빼면 규정 미달 타자 PA 가 없어 전체 리그 BB%·K% 는 `unavailable`. 2025 도 미완결 선수가 있어 `unavailable` |

API 단계에서의 교체안(결정 필요)

1. **표시 교체(권장)**: 홈 카드의 BB%·K% 를 '근사 BB%·K% (PA ≈ AB+BB+HBP, 희생타 제외)' 로 이름을 바꾸고 각주를 단다 — 값은 그대로, 오해만 없앤다.
2. **규정 타석 모집단으로 한정**: 규정 이상 타자(KBO 기록실 PA 연결 94%)만으로 `league_rate` 를 내고 '규정 타석 타자 기준' 으로 표시 — 미연결 선수가 있으면 그 시즌은 `unavailable`.
3. 리그 전체 정확값은 PA·SF 를 주는 자료가 생기기 전에는 내지 않는다.
