# 매크로 모니터

증권사 앱이나 일반 알림에서 잘 보이지 않는 매크로·크레딧·유동성 지표 33개를 매일 수집하고,
평소 범위를 벗어난 움직임을 **표시만** 하는 개인용 대시보드입니다.

- **감지만 하고 해석은 하지 않습니다.** "z-score +2.3, 5영업일 +85bp"처럼 사실만 적고, 국면 판단이나 투자 시사점은 쓰지 않습니다.
- 평일 하루 2회(07:30, 17:00 KST) GitHub Actions에서 실행됩니다.
- 결과는 GitHub Pages(`https://kimmzero62.github.io/dgfc-code/`)에 게시됩니다.
- 새 플래그가 생기면 GitHub 이슈로 알립니다. 텔레그램 시크릿이 등록돼 있으면 **매 실행마다 요약**(수집 현황, 새 플래그 내용, 이어지는 플래그 이름)을 텔레그램으로 보냅니다.

## 구조

```
config.yaml                 지표 목록과 감지 기준값 (여기만 고치면 됨)
manual/manual_inputs.csv    수동 입력 지표 (자동 수집이 안 되는 지표용, 현재 비어 있음)
data/macro.db               누적 시계열 (SQLite, 매 실행 후 자동 커밋)
macro_monitor/
  sources/                  수집기 (FRED, yfinance, 뉴욕연은, 재무부, 일본 재무성, DefiLlama, 금투협, worldgovernmentbonds, 수동)
  storage.py                SQLite 저장
  detect.py                 감지 (z-score, 백분위, 1년 고저, 변화폭 극단치)
  report.py                 HTML 대시보드
  notify.py                 GitHub 이슈 / 텔레그램 알림
  main.py                   실행 진입점
.github/workflows/monitor.yml
```

## 처음 설정

### 1. API 키를 GitHub Secrets에 등록

저장소 **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 필수 | 얻는 곳 |
|---|---|---|
| `FRED_API_KEY` | 필수 | https://fredaccount.stlouisfed.org/apikeys (무료 가입 → Request API Key) |
| `TELEGRAM_BOT_TOKEN` | 선택 | 텔레그램 [@BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_CHAT_ID` | 선택 | 텔레그램 [@userinfobot](https://t.me/userinfobot)이 알려주는 Id (봇에게 먼저 START를 눌러야 함) |

키는 코드나 파일에 적지 마세요. `.env` 등은 `.gitignore`로 막혀 있습니다.
FRED는 키 없는 CSV 경로가 GitHub Actions IP에서 응답하지 않아 공식 API 키가 필요합니다.

### 2. GitHub Pages 켜기

**Settings → Pages → Build and deployment → Source: GitHub Actions**
(무료 계정은 저장소가 공개여야 Pages를 쓸 수 있습니다.)

### 3. 첫 실행

**Actions → macro-monitor → Run workflow** 를 누르면 바로 실행됩니다. 첫 실행 때 지표별로 과거 약 800일치를 백필합니다.

## 감지 기준

`config.yaml`의 `defaults`가 모든 지표에 적용되고, 지표별로 `thresholds:`를 적으면 그 지표만 덮어씁니다.

| 항목 | 기본값 | 설명 |
|---|---|---|
| `z_threshold` | 2.0 | 최근 1년 값 분포 대비 \|z-score\| 이상이면 플래그 |
| `change_z_threshold` | 3.0 | 직전 대비 / 5영업일 변화가 과거 1년 변화 분포 대비 \|z\| 이상이면 플래그 |
| `flag_new_high_low` | true | 최근 1년 고점·저점 갱신 시 플래그 |
| `min_history_days` | 180 | 이력이 이보다 짧으면 감지하지 않고 '데이터 부족' 표시 |
| `stale_days` | 일간 5 / 주간 12 | 마지막 관측 후 이 일수가 지나면 ◷ 표시 (플래그 아님) |

```yaml
# 예: CCC OAS만 z 기준을 2.5로
- {id: ccc_oas, ..., thresholds: {z_threshold: 2.5}}
```

같은 지표·같은 관측일·같은 플래그 조합은 한 번만 '새 플래그'로 알립니다(주간 지표가 일주일 내내 알리지 않도록). 텔레그램 요약에서는 이런 지표를 '이전부터 이어지는 플래그'에 이름만 적습니다. 요약 없이 새 플래그만 받으려면 `alerts.telegram_summary: false`로 바꾸세요.

텔레그램 연결은 **Actions → macro-monitor → Run workflow**에서 "텔레그램 연결 테스트 메시지 보내기"를 체크해 확인할 수 있습니다.

## 지표와 소스

| 분류 | 지표 | 소스 | 비고 |
|---|---|---|---|
| 미국 금리·커브 | 30년물, 10Y-2Y, 10Y 실질금리 | FRED API | |
| | 10Y 텀프리미엄 | 뉴욕연은 ACM 엑셀 | 수일 지연 발표 |
| | MOVE | yfinance `^MOVE` | |
| 미국 크레딧 | IG / HY / CCC 이하 OAS | FRED API (ICE BofA) | |
| | BKLN 가격 | yfinance | |
| | BKLN NAV 대비 괴리율 | yfinance `navPrice` | NAV 이력을 무료로 받을 곳이 없어 **매 실행마다 누적**. 약 6개월 뒤부터 감지 |
| 달러 유동성 | TGA | 재무부 Daily Treasury Statement API | |
| | 지급준비금 | FRED `WRESBAL` | 주간 |
| 글로벌 | 엔/달러 | yfinance `JPY=X` | |
| | 일본 30년물 | 일본 재무성 CSV | |
| 국가 CDS (5년) | 미국, 독일, 프랑스, 이탈리아, 스페인, 영국, 일본, 중국, 한국 | worldgovernmentbonds.com | 국가 페이지의 historical API. 주말 값은 제외. 나라 추가는 `config.yaml`에서 `params.country`에 사이트 URL의 국가명(예: `brazil`)을 넣으면 됨 |
| 크립토 | 스테이블코인 시총 | DefiLlama | |
| 한국 | 회사채 AA-·BBB- 3년, CD 91일 | 금융투자협회 채권정보센터 최종호가수익률 | 키·로그인 불필요 |
| 레짐 상징 기업 | ORCL, CRWV, OWL, BX, APO, ARES | yfinance | |

외국인 순매수는 제외했습니다(KRX 데이터가 로그인을 요구함).

### 수동 입력

자동 수집이 안 되는 지표가 생기면 GitHub 웹에서 `manual/manual_inputs.csv` 를 열고 연필 아이콘으로 한 줄씩 추가합니다.

```
date,key,value
2026-10-10,my_key,24.5
```

`config.yaml`에 `source: manual` 지표를 만들고 `params.key`를 그 키로 지정하세요.

## 로컬 실행

```bash
pip install -r requirements.txt
export FRED_API_KEY=...       # 셸에서만, 파일로 저장하지 않기
python -m macro_monitor.main --out site --no-notify
python -m pytest -q
```

## 실패 처리

- 한 소스가 실패해도 나머지는 계속 수집하고, 실패한 지표는 페이지에 `✕ 수집 오류`로 표시합니다.
- 워크플로가 실패(빨간색)로 끝나는 건 **모든 지표 수집이 실패했을 때**뿐입니다.
- 공개 저장소는 60일간 활동이 없으면 스케줄이 멈추는데, 매 실행마다 DB를 커밋하므로 보통 해당되지 않습니다.
