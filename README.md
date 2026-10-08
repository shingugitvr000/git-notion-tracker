# Git 활동 대시보드 — GitHub Pages용

압축을 풀어 GitHub 저장소 루트에 그대로 커밋하면 됩니다. 별도 설치나 빌드 과정이 없는 순수 HTML·CSS·JavaScript 사이트입니다.

## 1. 실제 데이터 연결

학생 목록을 별도로 입력하지 않습니다. `tracker.py`가 기존 Notion 프로젝트 DB에서 `사용 여부`가 체크된 프로젝트만 읽습니다. Notion은 추적할 프로젝트 목록을 읽는 용도로만 사용하며, 커밋 행은 더 이상 Notion DB에 추가하지 않습니다.

기존 `git-notion-tracker` 저장소에서 사용하던 `NOTION_TOKEN` 값을 이 저장소의 `Settings → Secrets and variables → Actions`에도 같은 이름으로 등록하세요. GitHub의 비밀값은 저장소마다 따로 등록해야 합니다.

## 2. GitHub Pages 켜기

저장소의 `Settings → Pages → Build and deployment → Source`에서 `GitHub Actions`를 선택합니다. `Actions` 탭에서 `Sync Notion Git data and deploy Pages`를 한 번 실행하면 주소가 생성됩니다.

30분마다 Notion 프로젝트 목록과 GitHub 커밋을 동기화하고 Pages를 갱신합니다. `Actions → Run workflow`로 즉시 갱신할 수도 있습니다.

## 3. 데이터 흐름

`Notion 프로젝트 DB → tracker.py → GitHub 커밋 수집 및 작성자 검증 → data/students.json + data/commit-audit.json 생성 → GitHub Pages 배포` 순서로 동작합니다.

`data/commit-audit.json`에는 등록된 GitHub ID(`expectedGithub`)와 실제 GitHub 작성자(`actualGithub`)를 별도로 기록합니다. `verification` 값은 `verified`(일치), `mismatch`(다른 계정), `unlinked`(GitHub 계정 연결 확인 불가) 중 하나입니다.

대시보드의 커밋 수와 최근 커밋도 `verified` 항목만 집계하므로, 같은 저장소에서 작업한 다른 계정의 커밋은 학생 활동으로 표시되지 않습니다.

## 4. Notion 임베드

생성된 Pages 주소를 복사하고 Notion에서 `/embed`에 붙여넣습니다.

## 상태 기준

- 정상: 마지막 커밋 3일 이내
- 확인 필요: 4~7일
- 미활동: 8일 이상 또는 수집 실패

교수 평가, 학생 회고, 결과물 링크와 개인정보는 GitHub Pages에 넣지 말고 Notion에서 관리하세요.
