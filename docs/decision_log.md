# 개발 결정 기록 (Decision Log)

이 문서는 구현 중 내려진 판단과 그 근거를 남긴 것이다.
코드와 커밋 메시지만으로는 "왜 이렇게 했는가"가 복원되지 않는 항목들을 모았다.

- 계획: [plan.md](./plan.md) · 기술 조사: [research.md](./research.md)
- 브랜치 `feat/ebook-capture`, 26개 커밋, 분기점 `5fc0ab5`
- 최종 테스트: 81 passed, 2 deselected (manual)

Spec: docs/research.md (읽음). Branch: feat/ebook-capture. Base commit: 5fc0ab5.

## Pre-flight 충돌 스캔

### 파일/인터페이스를 공유하는 Task 쌍

| 생산 | 소비 | 인터페이스 | 결과 |
|---|---|---|---|
| T1 display.DisplayInfo | T2 Region.from_display | `left/top/width/height` 필드 | 일치 |
| T1 display.list_displays | T10 cli._choose_display | `list[DisplayInfo]` | 일치 |
| T2 Region | T4 capture.grab | `to_mss()` dict | 일치 |
| T2 Region | T8 pick_region | `from_points()` | 일치 |
| T2 Region | T9 SessionConfig | dataclass 필드 | 일치 |
| T3 page_filename | T4 save_page | `(title, page) -> str` | 일치 |
| T3 sort_pages/parse_page_number | T5 collect_pages | `list[Path] -> list[Path]` | 일치 |
| T3 sanitize_title | T10 cli._configure | `str -> str` | 일치 |
| T4 save_page | T5 테스트 `_make_pages` | 동일 시그니처 | 일치 (T4가 먼저) |
| T4 save_page | T9 run_session | `(img, dir, title, page, quality, dpi)` | 일치 |
| T5 build_pdf | T10 cli.main | `(dir, title, page_size)` | 일치 |
| T6 read_percent | T9 run_session | `Image -> float\|None` | 일치 |
| T6 StillnessDetector.update | T9 run_session | `Image -> bool` | 일치 |
| T7 click(x, y) | T10 cli.main | `lambda pt: click(*pt)` 어댑팅 | 일치 |
| T8 AbortWatcher.aborted | T9 run_session | `bool` 속성 | 일치 |
| T9 SessionConfig | T10 cli._configure | 생성자 인자 | 일치 |

### Task 자체 정합성 (테스트 vs 코드 vs 파일)

| Task | 결과 |
|---|---|
| T1 | 테스트 4개가 `check_permissions`/`list_displays`/`DisplayInfo.scale`를 덮음. 일치 |
| T2 | **불일치 발견 F-1** — `from_display`가 Produces에 있으나 테스트 없음 |
| T3 | 테스트 7개가 4개 공개 함수를 모두 덮음. 일치 |
| T4 | 일치. `test_grab_detects_blank_capture`가 권한 실패를 잡음 |
| T5 | 일치. A4/자연 크기 단언값은 컨트롤러가 실측 검증함 |
| T6 | 일치. 정지 감지 단언 `[F,F,F,T]` 실측 검증함 |
| T7 | 일치. manual 마커로 실제 클릭 테스트 분리 |
| T8 | 일치. monkeypatch 대상이 모듈 전역이라 동작 |
| T9 | **불일치 발견 F-2** — Interfaces에 `naming.sanitize_title` 소비로 적혔으나 실제 소비자는 T10 |
| T10 | **관찰 F-3** — `RESULT_DIR`이 `parents[2]` 상대경로라 editable 설치 전제 |
| T11 | 문서 Task. 일치 |

### 사전 Ruling

- **Ruling: T1 Step 1의 `git init`은 이미 컨트롤러가 수행했다** — 저장소는 `feat/ebook-capture` 브랜치로 존재하고 docs는 5fc0ab5로 커밋됨. 구현자는 `git init`과 `git checkout -b`를 실행하지 않고 나머지(디렉터리 생성, .gitignore)만 수행한다. — 틀렸을 경우 비용: 없음(`git init` 재실행은 무해하나 브랜치가 뒤바뀔 위험 제거)
- **Ruling: F-1 — T2에 `from_display` 테스트를 추가한다** — 공개 인터페이스는 테스트로 덮는 것이 계획서 자체 원칙이고, 리뷰어가 미테스트 공개 메서드를 결함으로 볼 것이다. `DisplayInfo`를 import하지 않도록 간단한 stub 객체로 테스트한다. — 틀렸을 경우 비용: 테스트 1개 추가 (되돌리기 쉬움)
- **Ruling: F-2 — 문서 오류로 판정, 코드 변경 없음** — `run_session`은 `sanitize_title`을 쓰지 않는다. T9 Interfaces 문구만 부정확하며 구현에 영향이 없다. 구현자에게 해당 줄을 무시하라고 전달한다. — 틀렸을 경우 비용: 없음
- **Ruling: F-3 — `parents[2]` 유지** — `pyproject.toml`이 editable 설치(`pip install -e`)를 전제하고 `[project.scripts]`로만 실행되므로 정상 동작한다. 배포 패키징은 이 계획의 범위 밖이다(YAGNI). — 틀렸을 경우 비용: 추후 wheel 배포 시 `RESULT_DIR` 해석 로직 1곳 수정

## 진행 기록

### Task 1
- 구현: 커밋 `0d06d67`. 테스트 `tests/test_display.py` 4/4 통과. pyautogui·numpy 부재 확인됨.
- 리뷰: Spec ✅ / 품질 Approved. Important 1건, Minor 2건.
- **Ruling: Important "display.py의 `import sys`가 죽은 코드" — 삭제한다.** 계획서 코드 블록에 내가 잘못 넣은 것으로, spec(research.md)은 이를 요구하지 않는다. 계획서 본문도 함께 수정했다. — 틀렸을 경우 비용: import 한 줄 복구
- **Ruling: Minor "uv.lock 미추적" — 커밋한다.** uv 프로젝트의 재현 가능한 설치를 위해 락파일은 추적하는 것이 표준이고 .gitignore도 이를 제외하지 않는다. 브리프의 git add 목록은 락파일 생성 전에 작성된 것이라 누락된 것뿐이다. — 틀렸을 경우 비용: `git rm --cached uv.lock` 한 번
- **Ruling: Minor "테스트 4개 중 3개가 스텁에도 통과함" — 이번 Task에서는 수정하지 않고 파킹한다.** 리뷰어 지적이 타당하나, 이 테스트들은 실제 Quartz API 호출 결과의 형태를 검증하는 스모크 테스트이고 display.py는 OS 조회를 그대로 위임하는 얇은 계층이다. 더 강한 단언(예: 특정 해상도)은 이 머신에 종속되어 오히려 깨지기 쉽다. — 틀렸을 경우 비용: display 계층의 회귀를 테스트가 못 잡음(영향 범위가 좁음)
- 수정 라운드 1/5: 2건 모두 반영, 0건 미해결 (커밋 `0d06d67`..`8fa6d63`)
- 재리뷰: PASS — 두 건 모두 ADDRESSED, 신규 breakage 없음. uv.lock에 pyautogui·numpy 모두 부재 확인.
- **Task 1: complete (commits 4ae7aca..8fa6d63, review clean)**
- 남은 인간 확인 항목: `uv run python scripts/preflight.py` 실사 실행 (대화형이라 에이전트 실행 불가). research.md 6.5 항목 1.
- 컨트롤러 커밋 `1d66951`: 계획서 본문의 `import sys` 제거.

### Task 2+3 (배치)
- 배치 사유: 둘 다 OS 비의존 순수 함수 모듈이고 브리프에 코드·테스트가 전량 포함된 전사 작업. 상호 의존 없음.
- 구현: Task 2 `e3f347f` (geometry 7/7), Task 3 `4dfd6b9` (naming 7/7).
- 리뷰: Spec ✅ (양쪽) / 품질 **Not approved** — Critical 1건, Minor 1건.
- **Ruling: Critical "`sort_pages`가 페이지가 아닌 파일이 섞이면 TypeError로 죽는다" — 수정한다.** 리뷰어 지적이 정확하다. 컨트롤러가 직접 재현 확인함: `sort_pages([t_p10.jpg, t.pdf, t_p2.jpg])` → `TypeError: '<' not supported between instances of 'NoneType' and 'int'`. 걸러내기가 `sorted()` 뒤에 있어 늦다. `result/`에는 최종 `.pdf`와 미리보기 `.png`가 같은 폴더에 생기므로 가설이 아니라 실제 경로다. 계획서 본문도 수정했다(필터를 walrus로 정렬 전에 이동, 혼합 입력 테스트 추가). — 틀렸을 경우 비용: 없음. 버그 수정이며 기존 계약은 그대로다.
- **Ruling: Minor "`sanitize_title` 독스트링이 '제거한다'인데 실제로는 밑줄로 치환" — 같은 라운드에서 함께 고친다.** 별도 라운드를 돌 가치는 없으나 이미 같은 파일을 여는 김에 한 단어를 바로잡는 편이 싸다. — 틀렸을 경우 비용: 없음
- 수정 라운드 1/5: 2건 모두 반영, 0건 미해결 (커밋 `4dfd6b9`..`9884deb`). 컨트롤러 직접 재현 확인: 혼합 입력 → `['t_p2.jpg','t_p10.jpg']`, 빈 입력 → `[]`.
- 재리뷰: PASS — 두 건 ADDRESSED, 신규 breakage 없음, geometry.py 무변경.
- **Task 2: complete (commits 1d66951..e3f347f, review clean)**
- **Task 3: complete (commits e3f347f..9884deb, review clean)**

### Task 4+5+6 (배치)
- 배치 사유: 셋 다 모듈 1개 + 테스트 1개의 전사 작업이고 브리프에 코드가 전량 포함됨. T5 테스트가 T4의 `save_page`를 소비하므로 순서 의존이 있어 같은 에이전트가 순서대로 수행하는 편이 안전하다.
- 구현: T4 `62969af` (5/5), T5 `c1c2419` (7/7), T6 `192feb4` (8/8). 전체 39 passed.
- 리뷰: Spec ✅ (3개 전부) / 품질 Approved. Important 1건, Minor 2건.
- **Ruling: Important "`read_percent` 정규식이 숫자 조각을 잡아 오인식" — 수정한다. `%` 기호를 필수로 요구하도록 앵커링.** 리뷰어 지적이 정확했고 컨트롤러가 실증했다. 실제 위험이 가설보다 크다: `'p 100 / 350'` → `100.0`을 반환해 **350쪽짜리 책을 100쪽에서 조기 종료**시킨다. OCR 영역에 쪽 번호가 조금이라도 겹치면 발생한다. 수정안(`(\d{1,3}(?:\.\d+)?)\s*%`)을 컨트롤러가 검증: `0%/47%/100%/99.8%`는 그대로 읽고 `'3 / 128'`·`'p 100 / 350'`·`'999'`·`'150%'`는 모두 None. research.md 6.2가 이 뷰어의 표기를 "정수 + % 기호"로 문서화했으므로 spec 정합적이다. — 틀렸을 경우 비용: `%` 없이 진행률을 표시하는 뷰어에서는 항상 None이 되어 정지 감지 폴백으로 종료(안전하게 성능만 저하)
- **Ruling: Minor "`mss.mss()` deprecation" — 함께 고친다.** `mss.MSS()`가 10.2.0에 존재하고 경고 없이 동작함을 확인했다. 향후 릴리스에서 제거 예정이라 방치하면 나중에 깨진다. 한 줄이고 같은 라운드에 묶는 편이 싸다. — 틀렸을 경우 비용: 한 줄 되돌리기
- **Ruling: Minor "`collect_pages`의 이중 필터링" — 파킹한다.** `sort_pages`가 이미 거르므로 중복이나 무해하고, 방어적 필터가 glob 패턴의 의도를 문서화하는 면도 있다. 이걸 고치려고 라운드를 더 도는 것은 이득이 없다. — 틀렸을 경우 비용: 없음(순수 가독성 문제)
- 수정 라운드 1/5: 2건 모두 반영 (커밋 `192feb4`..`71ac8e4`). 전체 41 passed, 경고 0. 컨트롤러 직접 확인: `0%`→0.0, `100%`→100.0, `99.8%`→99.8, `'p 100 / 350'`→None, `'3 / 128'`→None.
- 재리뷰: PASS — 두 건 ADDRESSED, `group(1)` 올바름, psm 7→8 재시도 보존, 잔존 `_NUM_RE` 참조 없음, pdfbuild 무변경.
- **Task 4: complete (commits 14153db..71ac8e4, review clean)**
- **Task 5: complete (commits 62969af..c1c2419, review clean)**
- **Task 6: complete (commits c1c2419..71ac8e4, review clean)**

### Task 7+8 (배치)
- 배치 사유: 둘 다 OS 연동 얇은 래퍼 모듈 1개 + 테스트 1개. 브리프에 코드 전량 포함. 상호 의존 없음.
- 위험: T8의 pynput 리스너 테스트가 pytest 환경에서 블로킹될 가능성. 구현자에게 행 발생 시 무시하지 말고 보고하도록 지시함.
- 구현: T7 `c341f2e` (4/4), T8 `342b048` (4/4). 전체 49 passed, 2 deselected(manual), 행 없음.
- 리뷰: Spec ✅ (양쪽) / 품질 Approved. Critical·Important 0건, Minor 6건(전부 "확인했고 문제없음" 성격).
- ⚠️ 항목 "AbortWatcher 테스트가 리스너 스레드를 누수하는가" — **컨트롤러가 직접 검증해 해소**.
  - 스레드 누수: **없음**. 단일 AbortWatcher는 진입·트리거·종료 모두 정상.
  - 대신 별개 사실 발견: 한 프로세스에서 **pynput 키보드 리스너를 3~4회 반복 생성하면 SIGABRT(exit 134)**. 횟수가 불규칙해 경합으로 보인다. 마우스 리스너는 6회 반복해도 정상.
  - **실제 CLI 1회 실행 시나리오 검증: 마우스 리스너 6회 + 키보드 리스너 1회 연속 = 전체 통과.** `pick_point`가 5회, `AbortWatcher`가 1회 쓰므로 프로덕션 경로는 안전하다.
- **Ruling: T7/T8 코드는 수정하지 않는다. 대신 "AbortWatcher는 프로세스당 1회만 진입한다"를 T9·T10 디스패치에 제약으로 전달한다.** 이는 T7/T8 코드의 결함이 아니라 pynput/macOS의 플랫폼 한계이고, 프로덕션 경로는 실측으로 안전함을 확인했다. 재사용 가능한 싱글턴으로 만드는 것은 YAGNI다. — 틀렸을 경우 비용: 훗날 AbortWatcher를 루프 안에서 재진입하는 코드를 누가 추가하면 런타임 abort. 원장과 최종 요약에 남겨 가시화한다.
- **Task 7: complete (commits c0b413f..c341f2e, review clean)**
- **Task 8: complete (commits c341f2e..342b048, review clean)**

### Task 9
- 구현: `58ede1c`. 55 passed, **1 failed** (`test_session_respects_max_pages`), 2 deselected.
- 구현자가 브리프 결함을 발견하고 통과시키려 로직을 약화시키지 않음 — 지시대로 정확히 행동함.
- **Ruling: Critical(테스트 픽스처) "`FakeCapturer` 기본 shade 단계 7이 정지 감지 오판을 일으킨다" — 픽스처를 고친다(단계 53). 프로덕션 코드는 건드리지 않는다.** 컨트롤러 실측: RGB `(shade,60,90)`에서 ΔR=7 → `convert('L')` 휘도 차이가 **정확히 2.0**이고 `StillnessDetector`의 `mean_diff <= 2.0` 조건에 걸려 매 프레임 "정지"로 집계된다. 그래서 `max_pages=5`에 닿기 전 4쪽에서 STILL로 종료한다. 단계를 53으로 바꾸면 휘도 차이 16 이상이라 명확히 구분된다(실측). 이는 **테스트 픽스처의 결함이지 프로덕션 결함이 아니다** — 실제 화면 캡처에서 전체 이미지 평균 휘도 차이 2.0은 안티에일리어싱 잡음 수준이라 threshold 2.0은 적절하다. 계획서 본문도 수정했다. — 틀렸을 경우 비용: threshold를 낮춰야 했던 것이라면 실사용에서 정지 감지가 늦게 걸림(조기 종료가 아니라 지연이므로 안전한 방향)
- 수정 라운드 1/5: 픽스처 결함 1건 반영 (커밋 `58ede1c`..`515542e`). 56 passed, 0 failed.
- 리뷰: Spec ✅ / 품질 Approved. Important 1건, Minor 1건.
- **Ruling: Important "'멈춘 뒤 클릭 안 함'이 COMPLETE 경로에서만 검증된다" — 나머지 세 경로에도 클릭 수 단언을 추가한다.** 이 도구의 최악 실패가 폭주 클릭이고, STILL·MAX_PAGES·ABORTED 테스트는 `clicker_fn=lambda p: None`이라 클릭을 아예 세지 않았다. 브리프 테스트 본문의 공백이지 구현자 책임이 아니다. 컨트롤러가 실제 기대값을 실측: COMPLETE/STILL/MAX_PAGES는 `clicks == pages - 1`, ABORTED만 `clicks == pages`(ESC는 이미 클릭한 뒤 다음 회차 시작에서 감지되므로). 이 비대칭 자체가 올바른 동작이며 테스트로 고정할 가치가 있다. — 틀렸을 경우 비용: 없음. 테스트 단언 3줄 추가일 뿐 제품 코드 무변경
- **Ruling: Minor "COMPLETE 회차에서는 StillnessDetector가 갱신되지 않는다" — 파킹한다.** COMPLETE는 즉시 return이고 detector 인스턴스는 그대로 버려지므로 관측 가능한 영향이 없다. "매 회차 정확히 한 번 갱신"을 문자 그대로 맞추려고 코드를 바꾸는 것은 이득 없는 변경이다. — 틀렸을 경우 비용: 없음
- 수정 라운드 2/5: 1건 반영 (커밋 `515542e`..`89abb37`). 56 passed, 0 failed.
- 구현자 보고 "전체 스위트 실행 중 간헐적 크래시" — **컨트롤러가 정량화해 원인 규명**.
  - 순차 실행 **16회 연속 0 크래시** (exit 0, 56 passed).
  - 동시 실행 **9회 중 1회 크래시** (exit 134 = SIGABRT).
  - 크래시 지점: `pynput/_util/darwin.py:153 keycode_context` ← `pynput/keyboard/_darwin.py:272 _run`. macOS 텍스트 입력 소스 API를 여러 프로세스가 동시에 잡을 때 죽는다. **pynput 상류 한계이지 이 프로젝트 코드의 결함이 아니다.**
- **Ruling: 코드를 바꾸지 않고 파킹한다. 대신 문서화한다.** 두 가지 대안을 검토했다. (a) AbortWatcher 테스트를 `manual` 마커로 빼면 플레이키함은 사라지지만 **ESC 중단이라는 필수 안전 기능의 기본 커버리지를 잃는다** — 나쁜 거래다. (b) 가짜 리스너 주입은 컨텍스트 매니저 수명주기(`__exit__`가 리스너를 실제로 멈추는가)를 검증하지 못하게 된다. 프로덕션은 프로세스당 키보드 리스너 1개만 쓰고 그 시나리오(마우스 6 + 키보드 1)를 실측으로 통과 확인했으므로, 실제 위험은 낮다. — 틀렸을 경우 비용: CI에서 스위트를 병렬로 돌리면 간헐적 실패. Task 11 README와 Task 12 사용자 가이드에 "테스트 스위트를 동시에 여러 개 돌리지 말 것"을 명시하도록 지시한다.
- **Task 9: complete (commits 342b048..89abb37, review clean, 1 parked)**

### Task 10
- 구현: `1288bd2` (60 passed). 구현자가 `main()` 입력 처리 문제 3건을 스스로 보고함(통과시키려 숨기지 않음).
- 리뷰: Spec ✅ / 품질 Approved. Important 2건, Minor 2건. 컨트롤러가 네 번째 미보호 경로(`--resume` 로드)를 추가 발견.
- 수정 라운드 1/5: 4건 반영 (`1288bd2`..`0d0dfac`). 65 passed. 입력 가드 동작 직접 확인.
- 재리뷰: 3건 ADDRESSED, 신규 breakage 없음. **잔여 공백 2건 발견.**
- **Ruling: 잔여 공백 2건을 수정 라운드 2에서 마저 고친다. 파킹하지 않는다.** 둘 다 방금 고친 Finding 1과 **동일한 부류**(사용자에게 한국어 대신 트레이스백 노출)이므로 절반만 고친 채 두는 것은 일관성이 없다. 컨트롤러가 둘 다 재현함: (1) `input()`이 `EOFError`를 던지면(stdin이 터미널이 아닐 때) `_ask*` 헬퍼에서 그대로 전파되어 트레이스백이 뜬다 — 프로브 실행 중 실제로 발생했다. (2) `_ask_index(prompt, 0)`은 어떤 입력도 `0 <= i < 0`을 만족하지 못해 "0 부터 -1 사이" 라는 말이 안 되는 안내를 무한 반복한다. 비용이 작고(각 몇 줄) 같은 결함군을 완전히 닫는다. — 틀렸을 경우 비용: 없음. 가드 추가일 뿐 기존 동작 무변경
- 수정 라운드 2/5: 2건 반영 (`0d0dfac`..`75a5573`). 68 passed, 0 failed, 2 deselected.
- 재리뷰: PASS — 두 건 ADDRESSED. `cli.py`의 `input(` 호출 2곳 모두 EOF 보호됨. 확인 프롬프트의 EOF는 '취소'로 귀결(진행 아님)이고 테스트가 이를 판별력 있게 검증함. 신규 breakage 없음.
- **Task 10: complete (commits 89abb37..75a5573, review clean)**

### 컨트롤러 실사용 검증 (클릭 없음)
사용자 요청으로 Task 11 이전에 컨트롤러가 직접 수행. 실제 클릭은 하지 않음.
- 권한: 화면 기록 True, 손쉬운 사용 True.
- 디스플레이 3대 정상 인식, 전부 scale 1.00x.
- **실제 화면 캡처 -> 300dpi JPEG 저장 -> OCR -> 정지 감지 -> PDF** 전 구간 통과.
  - 4장 캡처, 종료사유 `STILL`(클릭을 안 했으니 화면이 안 바뀌어 폴백이 정확히 작동), 클릭 3회(= pages-1), 2.3초.
  - JPEG 900x1200, dpi (300,300) 확인.
  - PDF 4쪽 0.47MB, 페이지 76x102mm, 내장 이미지 900x1200 `/DCTDecode`(무손실) 확인.
- **실제 뷰어 스크린샷으로 `read_percent` 판독 = 0.0** — 출하 코드가 진짜 UI에서 동작함을 확인.
- CLI 오류 경로 실행: `--help`(exit 0), `--page-size letter`(exit 2, argparse), 없는 `--resume`(exit 1, 한국어), 깨진 JSON `--resume`(exit 1, 한국어).
- **컨트롤러 실수 기록**: EOF 동작을 확인하려고 stdin을 닫고 `main()`을 호출했으나, `pick_point`는 stdin이 아니라 마우스를 기다리므로 사용자의 실제 클릭 2개를 가로챘다. pynput 리스너는 수동 감시라 클릭을 차단하지 않아 대상 앱에는 정상 전달되었고 화면 변경은 없었다. 이후 반복하지 않는다.

### 컨트롤러 실사용 검증 2 — 실제 클릭 전달 + 본문 화면 분석
사용자가 "2번(컨트롤러가 안전한 좌표에 클릭)"을 선택하여 수행.

**클릭 전달 검증 (research.md 6.5 항목 1 해소)**
- 대상 선정: 화면을 캡처해 육안 확인 후 Dock 왼쪽·VS Code 아래의 빈 바탕화면 `(30, 1220)` 선택.
- `clicker.click(30, 1220)` 전송 → 자체 pynput 마우스 리스너가 `(30,1220) Button.left` 눌림/뗌 **양쪽 모두 정확한 좌표로 관측**.
- 클릭 전후 화면 평균 차이 2.686 (바탕화면만 클릭, 변경 없음). 커서를 원래 위치 `(1472,930)`로 복원 완료.
- **결론: `CGEventPost`가 실제 시스템 이벤트 스트림에 정확한 좌표로 클릭을 전달한다. 마지막 미검증 항목 해소.**

**실제 본문 화면 분석 (사용자 제공 스크린샷 3836x2160, 4K 모니터 거의 전체)**
- **2단 펼침 구성**: 한 화면에 좌/우 두 단의 본문. 클릭 한 번이 두 단을 함께 넘긴다.
- 흰 본문 영역: x 316~3515, y 55~2104 → **3200x2050 px**
- 300dpi 환산 시 PDF 페이지 **271 x 174mm** — 표지 스크린샷(창이 작았을 때) 기준 94x150mm에서 크게 개선.
  **창을 4K에서 최대화하라는 research.md 6.4의 조언이 실측으로 입증됨.**
- 진행률 줄: y 2015~2026 (글자 높이 12px). `6%`가 x 387~406, 그 뒤 x 418부터 절 제목이 같은 줄에 이어짐.
- 다음 페이지 화살표: 오른쪽 `(3556, 1079)`, 왼쪽 `(274, 1079)`. 본문 영역 바깥 좌우 여백, 세로 중앙.
- **`%` 앵커링 결정이 실제 화면에서 검증됨**: 출하된 `read_percent`로 4가지 영역 폭을 시험 —
  딱 맞게/여유있게/제목까지 포함/아주 넓게 **전부 `6.0`**. 옆의 한글 제목이 섞여도 흔들리지 않는다.
  (`%` 없이 숫자만 찾았다면 제목의 "2절"에서 2를 읽을 위험이 있었다.)

### Task 11+12 (배치)
- 구현: T11 `773cedf` (README + research.md §5/§6.5 갱신), T12 `7dc9140` (사용자 가이드).
- 리뷰: Spec ✅ (양쪽) / 품질 **Not approved** — Critical 1건.
- **Ruling: Critical "`--resume`이 실제로는 이어서 하지 않고 p001부터 덮어쓴다" — 문서가 아니라 제품을 고친다.**
  컨트롤러가 재현함: 1차 10쪽 중단 → 2차 재개 시 p001~p004를 덮어쓰고, p005~p010은 1차분이 그대로 남아
  **서로 다른 두 실행이 한 PDF에 뒤섞인다.** 사용자는 10쪽 PDF를 받고 정상이라 여긴다. 조용한 데이터 손상이다.
  이 위험은 `--resume`에 국한되지 않고 **같은 제목으로 재실행하면 언제든** 발생한다.
  문서만 고치는 선택지도 있었으나 기각했다: spec(research.md 3.3)이 "설정을 저장해 중단 후 재개가 가능하게 한다"를
  명시하므로 현재 동작은 spec 미달이고, 문서를 낮추면 푸트건이 그대로 남는다.
  — 틀렸을 경우 비용: `start_page` 파라미터 1개와 CLI 가드 1개를 되돌리면 됨. 기존 테스트는 `start_page=0`에서 불변.
- ⚠️ 항목 "preflight 출력 형식" — 컨트롤러 확인: `화면 기록   : True` 처럼 파이썬 bool을 출력한다. 가이드의 "True로 표시" 서술과 일치.
- 수정 라운드 1/5 (resume): 커밋 `b526dec`. 73 passed, 2 deselected (75 수집 = 68 + 7 신규).
  컨트롤러 직접 재현 확인: 1차 10쪽 → 재개 시 `p011,p012,p013`으로 이어지고 1차분 10쪽 보존.
  구현자가 컨트롤러의 테스트 개수 산술 오류(75 passed → 실제 73 passed + 2 deselected)를 바로잡음.
- 재리뷰: **APPROVE** — ADDRESSED, 신규 breakage 없음.
  - `max_pages`가 절대 페이지 번호 기준이라 1990에서 재개해도 2000에서 멈춤(잔여 개수 아님) 확인.
  - 덮어쓰기 가드가 `if/elif`라 `--resume`이 unlink에 도달할 수 없음 확인.
  - 거절·EOF 경로 모두 `return 1`이 unlink 앞에 있어 파일 보존 확인(테스트가 실제 파일 존재를 단언).
- **Task 11: complete (commits ae80043..773cedf, review clean)**
- **Task 12: complete (commits 773cedf..b526dec, review clean)**

### 최종 브랜치 리뷰 (opus, 25 커밋)
판정: **"명시된 수정 후 안전(Safe with named fixes)"**. Critical 1, Important 3, Minor 5.
- **Ruling: C1 "제목에 `[` `]`가 들어가면 glob이 깨져 전 산출물을 잃는다" — 즉시 수정.** 컨트롤러 재현 확인:
  `데이터베이스 입문[개정판]`은 `sanitize_title`을 통과하고 파일도 정상 저장되지만 `collect_pages`가 `[]`를 반환한다.
  glob에서 `[]`는 문자 클래스이기 때문이다. 결과: (a) PDF를 영영 만들 수 없고, (b) `latest_page_number`가 0이 되어
  덮어쓰기 가드와 `--resume`이 함께 눈이 멀어 **Task 11에서 막은 뒤섞임 버그가 재발한다.**
  한국어 전자책 제목에 `[개정판]`류는 흔하다. — 틀렸을 경우 비용: 없음. `glob.escape` 적용은 기존 파일 호환
- **Ruling: I2 "카운트다운 중에는 ESC가 동작하지 않는다" — 수정.** "중단하려면 ESC"라고 출력한 뒤 `time.sleep(5)`를 하는데
  `AbortWatcher`는 그 다음에 진입한다. 도구가 ESC가 된다고 말하는 바로 그 구간에서 안 되는 것은 최악의 조합이다.
  `AbortWatcher`가 카운트다운을 감싸도 프로세스당 리스너는 여전히 1개라 pynput 제약과 충돌하지 않는다.
- **Ruling: I3 "미리보기 확인 전에 파일을 지운다" — 수정.** `d` 동의 직후 unlink하는데, 이후 미리보기에서 영역이 틀린 걸
  보고 `n`을 누르면 옛 파일은 이미 사라졌고 새 캡처도 없다. 동의는 받았으나 순서가 불필요하게 파괴적이다.
- **Ruling: I4 "유일하게 데이터를 지우는 분기에 테스트가 없다" — 추가.** `d` 경로는 무커버리지다.
- **Ruling: M5(검은 화면 검사)는 '종료' 대신 '경고 후 미리보기 확인으로 진행'으로 구현한다.** research.md §5는 종료를 적었으나,
  정당하게 단색인 페이지에서 오탐으로 하드 종료하면 더 나쁘다. 경고 + 미리보기 파일 확인이 침묵 실패를 막는 목적을 달성한다.
  spec 문구와의 이 차이를 research.md에 명시하도록 지시한다.
- **Ruling: M6(scale != 1.0 런타임 환산·재개 시 재검증)은 파킹한다.** 이 머신의 3개 디스플레이가 모두 1.00x이고,
  리뷰어도 mss의 2x 동작을 확인하지 못해 "suspected"로 표기했다. 확인되지 않은 동작에 맞춰 코드를 넣는 것은 이르다.
  대신 재개 시 scale != 1.0이면 경고만 출력하도록 한다. — 틀렸을 경우 비용: Retina 네이티브 모드로 바꾼 사용자가
  옛 세션을 재개하면 좌표가 어긋남. 경고가 이를 가시화한다.
- 최종 수정 웨이브: 커밋 `443d4f9`. 81 passed, 2 deselected. C1·I2·I3·I4·M5·M7·M8·M9 반영, M6는 경고만.
  컨트롤러 확인: 신규 제목 `데이터베이스 입문[개정판]` → `데이터베이스 입문_개정판_`로 정제되고,
  **이미 대괄호로 저장된 기존 파일도 `glob.escape` 덕분에 그대로 찾아 PDF 생성 성공**(하위 호환).
- 최종 재리뷰(opus): **"사용자에게 전달해도 안전"**. 8건 전부 ADDRESSED.
  리뷰어가 변이 테스트로 검증: 삭제 시점 되돌리기·ESC 검사 제거·`last_page` 되돌리기를 각각 주입했을 때
  의도한 새 테스트가 정확히 실패함을 확인(3 failed, 16 passed). 테스트가 실제로 결함을 잡는다.
  `AbortWatcher` 생성은 `src/`+`scripts/` 전체에서 정확히 1곳.
- **Ruling: 잔여 minor 3건을 파킹한다.** (1) `d`→`y`→ESC 시 옛 페이지가 이미 지워짐 — 이중 동의를 거친 결과라
  일관적이다. (2) `path.unlink()`에 `missing_ok` 없음 — 동시 삭제라는 비현실적 조건에서만 발생. (3) `merged_pages`가
  PDF 쪽수가 아니라 디스크 파일 수 — `build_pdf`가 전량을 병합하므로 현재는 동일하다. 셋 다 두 번째 수정 웨이브를
  돌 가치가 없다. — 틀렸을 경우 비용: 각각 몇 줄의 후속 수정
