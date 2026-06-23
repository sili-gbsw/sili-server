# sili-server

**스팟용접 품질 관문 시스템 (Spot Welding Quality Gate)** 의 백엔드 API 서버입니다.  
PLC로부터 수집된 타점 데이터를 실시간으로 수신·채점하여, 이상 의심 부품을 자동으로 선별합니다.

> 2026 실리 경진대회 프로젝트

---

## 주요 기능

- **실시간 판정** — PLC 타점 데이터를 수신해 이상 점수(0~100)를 산정하고 🟢 정상 / 🟡 주의 / 🔴 재검권장 3단계로 분류
- **자동 학습** — 라인·부품별 정상 범위를 누적 데이터로 자동 학습하고 판정 기준을 환류(Feedback)
- **실시간 알림** — WebSocket 스트림으로 판정 결과를 즉시 푸시, REST 폴링 폴백 지원
- **재검 큐 관리** — 주의/재검권장 부품을 큐에 등록하고, 검사 결과를 입력·추적
- **대시보드 KPI** — 교대별 합격률·시간당 생산량·검사자 퍼포먼스 통계 제공
- **CSV 내보내기** — 타점 이력을 필터 조건에 따라 스트리밍 다운로드
- **부품 마스터** — 차종·부품별 재질, 두께, 품질 등급, 전극 형상 정보 CRUD

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| 데이터베이스 | MongoDB (Motor 비동기 드라이버 + Beanie ODM) |
| 스키마 검증 | Pydantic v2 |
| 서버 | Uvicorn |
| 컨테이너 | Docker / docker-compose |

---

## 프로젝트 구조

```
sili-server/
├── app/
│   ├── api/v1/          # REST 엔드포인트
│   ├── core/            # 설정, 예외, 공통 응답, OpenAPI 커스터마이징
│   ├── db/              # DB 세션 초기화
│   ├── models/          # Beanie Document 모델
│   ├── schemas/         # Pydantic 입출력 스키마
│   ├── services/        # 비즈니스 로직
│   └── main.py          # 앱 진입점
├── docs/                # 기능 명세서, 개발 순서
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 시작하기

### 사전 요구사항

- Python 3.12+
- MongoDB 6.0+ (로컬) 또는 MongoDB Atlas URI
- (선택) Docker & docker-compose

### 로컬 실행

```bash
# 1. 저장소 클론
git clone <repo-url>
cd sili-server

# 2. 가상환경 생성 및 의존성 설치
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 MongoDB URI 등을 수정

# 4. 서버 실행
uvicorn app.main:app --reload
```

서버가 기동되면 `http://localhost:8000` 에서 확인할 수 있습니다.

### Docker로 실행

```bash
# .env 파일 준비 후
docker-compose up --build
```

---

## 환경 변수

`.env.example` 를 참고하여 `.env` 파일을 작성하세요.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `MONGODB_URL` | MongoDB 연결 URI | `mongodb://localhost:27017` |
| `MONGODB_DB` | 데이터베이스 이름 | `sili` |
| `PROJECT_NAME` | 서비스 이름 | `Sili Server` |
| `PROJECT_VERSION` | API 버전 | `0.1.0` |
| `API_V1_PREFIX` | API 경로 prefix | `/api/v1` |

---

## API 문서

서버 기동 후 아래 URL에서 인터랙티브 API 문서를 확인할 수 있습니다.

| 문서 | URL |
|------|-----|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |

### 엔드포인트 요약

| 그룹 | 메서드 | 경로 | 설명 |
|------|--------|------|------|
| **헬스** | GET | `/` | 헬스 체크 |
| **타점 이벤트** | POST | `/api/v1/weld-events` | 타점 데이터 수신 + 즉시 판정 (PLC) |
| | GET | `/api/v1/weld-events` | 타점 이력 조회 (필터·페이지네이션) |
| **판정** | GET | `/api/v1/judgements/{event_id}` | 판정 결과 상세 조회 |
| **부품 마스터** | GET/POST | `/api/v1/parts` | 부품 목록 조회 / 등록 |
| | GET/PATCH/DELETE | `/api/v1/parts/{part_id}` | 부품 단건 조회·수정·삭제 |
| **재검 큐** | GET/POST | `/api/v1/reinspection` | 재검 큐 조회 / 등록 |
| **학습** | POST | `/api/v1/learning/start` | 정상 범위 학습 시작 |
| | GET | `/api/v1/learning/{line_id}` | 라인별 학습 세션 조회 |
| | GET | `/api/v1/learning/{line_id}/history` | 학습 이력 조회 |
| | POST | `/api/v1/learning/reset` | 학습 세션 초기화 |
| **통계** | GET | `/api/v1/stats/shift` | 교대 합격률 + 시간당 생산 KPI |
| | GET | `/api/v1/stats/hourly` | 시간대별 판정 현황 |
| | GET | `/api/v1/stats/user-performance` | 검사자별 퍼포먼스 통계 |
| **알림** | GET | `/api/v1/events/latest` | 최신 판정 결과 폴링 |
| | WS | `/api/v1/ws/events` | 실시간 판정 결과 스트림 |
| | GET | `/api/v1/notifications` | 알림 이력 조회 |
| | POST | `/api/v1/notifications/mark-read` | 알림 읽음 처리 |
| **내보내기** | GET | `/api/v1/exports/weld-events.csv` | 타점 이력 CSV 다운로드 |
| **설정** | GET/PUT | `/api/v1/config` | 시스템 설정 조회·수정 |
| **사용자** | POST | `/api/v1/auth/login` | 로그인 |
| | GET/POST | `/api/v1/users` | 사용자 조회·등록 |

---

## 판정 로직

PLC에서 타점 데이터가 수신되면 아래 흐름으로 즉시 판정됩니다.

```
PLC → POST /weld-events
        ↓
   부품 마스터 조회
        ↓
   이상 점수 산정 (0~100)
        ↓
   ┌─────────────────────────────┐
   │ 0~39점  → 🟢 NORMAL        │
   │ 40~69점 → 🟡 CAUTION       │
   │ 70~100점→ 🔴 REJECT        │
   └─────────────────────────────┘
        ↓
   WebSocket 으로 결과 푸시
        ↓
   CAUTION/REJECT → 재검 큐 등록
```

---

## 테스트

```bash
pytest tests/
```
