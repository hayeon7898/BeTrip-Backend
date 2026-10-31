# 🌍 BeTrip Backend
 
여행지·인원·여행 스타일을 입력하면 일정을 자동으로 만들어 주고, 대화로 취향에 맞는 장소를 추천받아 바로 일정에 담을 수 있는 **여행 일정 플래너** 웹 서비스의 백엔드입니다.
 
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_async-D71F00)
![Gemini](https://img.shields.io/badge/Gemini-function_calling-8E75B2?logo=googlegemini&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-GHCR-2496ED?logo=docker&logoColor=white)
 
<br>

## 📌 목차
 
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [시스템 구조](#시스템-구조)
- [API](#api)
- [데이터베이스](#데이터베이스)
- [프로젝트 구조](#프로젝트-구조)
- [시작하기](#시작하기)
- [테스트와 평가](#테스트와-평가)
- [CI/CD](#cicd)
- [협업 규칙](#협업-규칙)
<br>

## 💡 주요 기능
 
| 기능 | 설명 |
| --- | --- |
| **일정 자동 생성** | 담아 둔 장소를 위치 기준으로 일자별로 나눕니다. (k-means)<br>하루 안에서는 이동 거리가 최소가 되는 순서로 정렬하고 오전, 점심, 저녁에 배치합니다.<br>장소 간 이동 시간은 카카오모빌리티 API로 계산합니다. |
| **대화형 장소 추천** | Gemini function calling으로 카카오맵과 한국관광공사 TourAPI를 연결합니다.<br>실제 검색 결과에 근거해 장소를 추천하며, 추천 카드에서 바로 일정에 담을 수 있습니다. |
| **취향 태그 검색** | 블로그 후기를 LLM으로 감성, 조용함, 뷰맛집 등 11종의 고정 태그로 분류합니다.<br>배치 워커가 미리 수행한 분류 결과를 활용해 "조용한 카페" 같은 질의를 처리합니다. |
| **지도 검색** | 카카오맵 키워드, 좌표, 영역 검색을 지원합니다.<br>장소 상세 정보와 썸네일(og:image)을 수집하고, 장소 간 이동 시간을 계산합니다. |
| **일정 편집** | 장소 담기와 삭제, 날짜 및 시간대 이동, 같은 날의 방문 순서 변경을 지원합니다.<br>변경 시 해당 일자의 방문 순서와 시작 시각을 다시 계산합니다. |
| **인증** | JWT Access Token과 회전(rotation)되는 Refresh Token(HttpOnly 쿠키)을 사용합니다.<br>동시 갱신 요청에 대응하기 위해 원자적 폐기와 재사용 유예 시간을 적용했습니다. |
 
<br>

## 🛠️ 기술 스택
 
| 분류 | 사용 기술 |
| --- | --- |
| Language | Python 3.12 |
| Framework | FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy 2.0 (async) + asyncpg, Alembic |
| LLM | Google Gemini (`google-genai`): function calling, structured output |
| 외부 API | 카카오맵/카카오모빌리티, 한국관광공사 TourAPI, 네이버 검색(블로그) |
| 비동기 작업 | APScheduler (태그 분류 배치) |
| 인증 | PyJWT, bcrypt |
| 테스트 및 품질 | pytest, pytest-asyncio, pytest-cov, Ruff, pre-commit, SonarCloud |
| 배포 | Docker, GitHub Actions, GitHub Container Registry |
 
<br>

## 🐟 시스템 구조
### 전체 구조
<img width="550" alt="image" src="https://github.com/user-attachments/assets/59b5d3d9-621a-4808-a3a9-87d92c6c1b82" />

### Backend 구조
 
```mermaid
flowchart LR
    FE[Frontend] -->|REST /api/v1| API[FastAPI Router]
 
    subgraph Backend
        API --> SVC[Service]
        SVC --> REPO[Repository]
        REPO --> DB[(PostgreSQL)]
        SVC --> CONV[ConversationService]
        SCHED[APScheduler<br/>태그 분류 배치] --> TAG[TagService]
        TAG --> REPO
    end
 
    CONV <-->|function calling| GEMINI[Gemini]
    CONV -->|search_places| KAKAO[카카오맵]
    CONV -->|search_tour_places| TOUR[TourAPI]
    SVC --> MOBILITY[카카오모빌리티]
    TAG --> NAVER[네이버 블로그 검색]
    TAG -->|태그 분류| GEMINI
```
 
1. **Router / Service / Repository** 3계층으로 나누고 의존성 주입(`Depends`)으로 연결합니다.
    - 서비스는 모킹한 단위 테스트로,
    - 레포지토리는 실제 PostgreSQL 통합 테스트로 검증합니다.
2. 카카오 검색 결과는 `places` 테이블에 캐싱되고, 배치 워커가 태그가 없거나 90일이 지난 장소를 골라 태그를 채웁니다.
   - 사용자 요청 경로에서는 LLM 분류를 호출하지 않습니다.
<br>

## 📄 API
 
모든 경로의 접두사는 `/api/v1`입니다. 서버 실행 후 [Swagger](http://localhost:8000/docs)에서 요청·응답 스키마를 확인할 수 있습니다. 인증이 필요한 API는 `Authorization: Bearer <access_token>` 헤더를 사용합니다.
 
### Auth
 
| Method | Path | 설명 | 인증 |
| --- | --- | --- | :---: |
| `POST` | `/auth/signup` | 회원가입 | |
| `POST` | `/auth/login` | 로그인, Access Token 발급 및 Refresh Token 쿠키 설정 | |
| `POST` | `/auth/refresh` | Refresh Token으로 토큰 재발급 (rotation) | 쿠키 |
| `POST` | `/auth/logout` | Refresh Token 폐기 | 쿠키 |
 
### Itineraries
 
| Method | Path | 설명 | 인증 |
| --- | --- | --- | :---: |
| `POST` | `/itineraries/conditions` | 여행 조건(지역, 날짜, 목적, 스타일 등)으로 일정 생성 | ✅ |
| `GET` | `/itineraries` | 내 일정 목록 | ✅ |
| `GET` | `/itineraries/{itinerary_id}` | 일정 상세 (일자·시간대별 장소) | ✅ |
| `DELETE` | `/itineraries/{itinerary_id}` | 일정 삭제 | ✅ |
| `POST` | `/itineraries/{itinerary_id}/plans/generate` | 담은 장소로 일정 자동 배치 | ✅ |
| `POST` | `/itineraries/{itinerary_id}/plans/save` | 배치된 일정 저장 | ✅ |
 
### Itinerary Places
 
| Method | Path | 설명 | 인증 |
| --- | --- | --- | :---: |
| `GET` | `/itineraries/{itinerary_id}/places/recommend` | 지역·목적·스타일 기반 장소 추천 (`category` 필터) | |
| `POST` | `/itineraries/{itinerary_id}/places` | 장소 담기 | |
| `DELETE` | `/itineraries/{itinerary_id}/places/{itinerary_place_id}` | 담은 장소 삭제 | |
| `PATCH` | `/itineraries/{itinerary_id}/places/reorder` | 같은 날 안에서 순서 변경 | |
| `PATCH` | `/itineraries/{itinerary_id}/places/{place_id}` | 다른 날짜·시간대로 이동 | |
 
### Map
 
| Method | Path | 설명 | 인증 |
| --- | --- | --- | :---: |
| `GET` | `/map/search` | 장소 검색 (`q`, `x`·`y`·`radius`, `rect`, `category`, `page`) | |
| `GET` | `/map/search/by-tags` | 캐싱된 장소를 취향 태그로 검색 (`tags`, `category`, `x`·`y`·`radius`) | |
| `GET` | `/map/places/{place_id}` | 장소 상세 | |
| `GET` | `/map/transit` | 두 지점 간 이동 시간 계산 | |
 
### Chat
 
| Method | Path | 설명 | 인증 |
| --- | --- | --- | :---: |
| `POST` | `/itineraries/{itinerary_id}/chat` | 대화형 장소 추천. <br> 응답에 답변 텍스트와 장소 카드(좌표, 태그 포함)를 함께 반환 | |
 
<br>

## 📊 데이터베이스
 
```mermaid
erDiagram
    users ||--o{ refresh_tokens : has
    users ||--o{ itineraries : owns
    itineraries ||--o{ itinerary_places : contains
    places ||--o{ itinerary_places : "referenced by"
    itineraries ||--o{ conversation_messages : has
 
    users {
        uuid user_id PK
        varchar email UK
        varchar password_hash
        varchar provider "LOCAL | KAKAO"
    }
    refresh_tokens {
        uuid token_id PK
        uuid user_id FK
        varchar token_hash "SHA-256"
        timestamptz expires_at
        timestamptz revoked_at
    }
    itineraries {
        uuid itinerary_id PK
        uuid user_id FK
        varchar status "DRAFT | GENERATED | SAVED"
        varchar region
        date start_date
        date end_date
        jsonb styles
    }
    places {
        varchar place_id PK "카카오 ID 또는 tour_ 접두사"
        varchar name
        varchar category "RESTAURANT | CAFE | ACTIVITY"
        float lat
        float lng
        jsonb tags "GIN jsonb_path_ops"
        timestamp tags_synced_at
    }
    itinerary_places {
        uuid itinerary_place_id PK
        uuid itinerary_id FK
        varchar place_id FK
        smallint day "NULL이면 미배정"
        varchar time_slot
        smallint order_in_day
        varchar start_time
    }
    conversation_messages {
        uuid message_id PK
        uuid itinerary_id FK
        varchar role
        text content
    }
```
 
설계 포인트는 다음과 같습니다.
 
- **담기와 배정을 한 테이블에서**: `itinerary_places`의 `day / time_slot / order_in_day`는 nullable이고, 배정된 슬롯에만 걸리는 부분 유니크 인덱스(`WHERE day IS NOT NULL`)로 중복을 막습니다.
- **태그 검색**: `places.tags`(JSONB)에 GIN(`jsonb_path_ops`) 인덱스를 두어 `@>` 포함 검색을 처리합니다.
- **토큰 보안**: Refresh Token은 원문 대신 SHA-256 해시만 저장합니다.
- **마이그레이션**: 스키마 변경은 Alembic으로 관리하며, 컨테이너 시작 시 `alembic upgrade head`가 자동 실행됩니다.
<br>

## 📁 프로젝트 구조
 
```
app/
├── api/v1/
│   ├── router.py            # 도메인별 라우터 등록
│   └── endpoints/           # auth, itineraries, itinerary_place, map, chat
├── core/
│   ├── config.py            # 환경변수 (pydantic-settings)
│   ├── security.py          # JWT, 비밀번호 해싱
│   ├── scheduler.py         # 태그 분류 배치 (APScheduler)
│   └── *_client.py          # 카카오, 네이버, TourAPI 클라이언트
├── db/                      # async 엔진·세션
├── models/                  # SQLAlchemy 모델
├── repositories/            # DB 접근
├── schemas/                 # 요청·응답 스키마 (Pydantic)
├── services/                # 비즈니스 로직
└── utils/
    └── itinerary_planner.py # 일자 클러스터링, 동선 정렬, 시간 배치
alembic/                     # 마이그레이션
scripts/
├── seed.sql                 # 시드 데이터
└── eval_tool_calling.py     # LLM tool calling 평가 스크립트
tests/
├── unit/                    # 서비스 단위 테스트 (모킹)
└── integration/             # 실제 PostgreSQL 대상 통합 테스트
```
 
<br>

## 🚀 시작하기
 
### 1. 환경변수
 
```bash
cp .env.example .env
```
 
| 변수 | 설명 | 필수 |
| --- | --- | :---: |
| `DATABASE_URL` | `postgresql+asyncpg://user:password@localhost:5432/betrip` | ✅ |
| `JWT_SECRET_KEY` | JWT 서명 키 | ✅ |
| `CORS_ORIGINS` | 허용할 프론트엔드 주소 (기본 `http://localhost:5173`) | |
| `COOKIE_SECURE` | 로컬 http는 `false`, 배포(https)는 `true` | |
| `KAKAO_REST_API_KEY` | 카카오맵·카카오모빌리티 | ✅ |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 네이버 블로그 검색 (태그 분류용) | ✅ |
| `GEMINI_API_KEY` | 대화형 추천, 태그 분류 | ✅ |
| `TOUR_API_KEY` | 한국관광공사 TourAPI | ✅ |
| `OPENAI_API_KEY` | 현재 코드에서 사용하지 않지만 설정 검증에 필요 | ✅ |
 
### 2-A. 로컬 실행
 
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
pre-commit install                # 커밋 시 ruff 자동 실행
 
alembic upgrade head              # 스키마 적용
psql "postgresql://user:password@localhost:5432/betrip" -f scripts/seed.sql   # 시드 (선택)
 
uvicorn app.main:app --reload
```
 
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

### 2-B. Docker 실행
 
이미지는 `main` 브랜치 푸시 시 GHCR에 자동으로 올라갑니다. 컨테이너는 시작할 때 마이그레이션과 시드 적용 후 서버를 띄웁니다.
 
```bash
docker pull ghcr.io/hyun7931/betrip-backend:latest
docker run --env-file .env -p 8000:8000 ghcr.io/hyun7931/betrip-backend:latest
```
 
<br>

## ✅ 테스트와 평가
 
```bash
pytest tests/unit            # 단위 테스트 (DB 불필요)
pytest                       # 통합 테스트 포함 (PostgreSQL 필요)
```
 
### LLM tool calling 평가
 
대화형 추천이 질의에 맞는 도구와 인자를 고르는지 평가셋으로 측정합니다. 도구를 실제로 실행하지 않아 DB 없이 `GEMINI_API_KEY`만으로 실행할 수 있고, 프롬프트나 도구 설명을 바꿀 때 회귀 확인용으로 사용합니다.
 
```bash
python scripts/eval_tool_calling.py                     # 기본 질의 24개
python scripts/eval_tool_calling.py \
    --cases scripts/eval_tool_calling_cases_hard.json \
    --repeat 5                                          # 경계 사례 15개, 5회 반복
```
 
| 평가셋 | 결과 |
| --- | --- |
| 기본 질의 24개 | 24/24 |
| 경계 사례 15개 × 5회 <br> (목록 밖 취향, 오타·영어, 도구 2개 필요, 지원 외 요청, 다중 턴 정정) | 74/75 → 도구 설명 수정 후 실패 케이스 <br> 10/10 |
 
<br>

## 🔗 CI/CD
 
| 워크플로 | 트리거 | 내용 |
| --- | --- | --- |
| `ci.yml` | `main`, `develop`대상 <br> push, PR | Postgres 서비스 컨테이너 → Ruff lint & format 검사 <br> → pytest(커버리지) → SonarCloud 품질 게이트 |
| `docker-build.yml` | `main` 대상 <br> push | Docker 이미지 빌드 후 GHCR 푸시 |
 
fork에서 올라온 PR은 시크릿이 전달되지 않으므로 SonarCloud 단계만 조건부로 건너뜁니다.
 
<br>

## 😺 협업 규칙
 
### 브랜치와 PR
 
이슈 생성 → 이슈별 브랜치 → PR(템플릿 사용) → CI 통과 후 `develop`에 머지합니다.
 
### 커밋 메시지
 
```
type: subject
 
- 무엇을 왜 변경했는지 (한 줄 72자 이내)
 
Closes #이슈번호
```
 
<details>
<summary>커밋 타입과 작성 규칙</summary>
| 타입 | 설명 |
| --- | --- |
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 기능 변화 없는 코드 구조 개선 |
| `docs` | 문서 수정 |
| `style` | 코드 스타일 수정 |
| `test` | 테스트 코드 추가 및 수정 |
| `chore` | 설정·빌드·패키지 등 유지보수 |
| `hotfix` | 운영 환경 긴급 수정 |
 
- 제목은 50자 이내, 끝에 마침표 금지
- 제목과 본문 사이 한 줄 공백
- 명령문 형태 사용 (예: 수정한다 X → 수정 O)
- 하나의 커밋에는 하나의 작업만 포함
- 커밋 내용은 한국어, 이슈 번호는 Footer에 작성
</details>

### 코드 스타일
 
커밋 시 pre-commit이 Ruff를 자동 실행합니다. 수동으로 실행하려면:
 
```bash
ruff check . --fix && ruff format .     # 자동 수정
ruff check . && ruff format --check .   # 검사만
```
