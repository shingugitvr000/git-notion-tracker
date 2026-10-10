import os
import json
import urllib.request
import urllib.error
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

COMMIT_DATA_SOURCE_ID = "3c28655a-72df-8076-a7aa-000b7d2948d4"
PROJECT_DATA_SOURCE_ID = "3c28655a-72df-8061-8782-000ba17e1ab9"

NOTION_VERSION = "2025-09-03"
SYNC_META_PATH = os.path.join("data", "sync-meta.json")
INCREMENTAL_COMMIT_LIMIT = 50
BACKFILL_PAGE_SIZE = 100
COMMIT_CACHE = {}


def request_json(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(
        url,
        method=method,
        headers=headers or {},
        data=json.dumps(data).encode("utf-8") if data is not None else None,
    )

    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print("HTTP ERROR:", e.code)
        print("URL:", url)
        print("BODY:", body)
        raise


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "git-notion-tracker",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def load_sync_metadata():
    if not os.path.exists(SYNC_META_PATH):
        return {}

    with open(SYNC_META_PATH, "r", encoding="utf-8") as file:
        metadata = json.load(file)

    if not isinstance(metadata, dict):
        raise ValueError("data/sync-meta.json must contain a JSON object")

    return metadata


def save_sync_metadata(metadata):
    os.makedirs("data", exist_ok=True)
    with open(SYNC_META_PATH, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)
        file.write("\n")

def get_project_repositories():
    url = f"https://api.notion.com/v1/data_sources/{PROJECT_DATA_SOURCE_ID}/query"

    # Notion에서 일단 전체 프로젝트를 가져온다.
    result = request_json(
        url,
        method="POST",
        headers=notion_headers(),
        data={}
    )

    print("Repo List 전체 행 수:", len(result.get("results", [])))

    repositories = []

    for page in result.get("results", []):
        props = page.get("properties", {})

        # 사용 여부 확인
        active = props.get("사용 여부", {}).get("checkbox", False)

        print("DEBUG 사용 여부:", active)

        if not active:
            continue

        github_id = ""
        repo_url = ""
        project_name = ""

        # GitHub ID
        rich_text = props.get("GitHub ID", {}).get("rich_text", [])
        if rich_text:
            github_id = rich_text[0].get("plain_text", "")

        # Repo URL
        repo_url = props.get("Repo URL", {}).get("url") or ""

        # 프로젝트명
        title = props.get("프로젝트명", {}).get("title", [])
        if title:
            project_name = title[0].get("plain_text", "")

        print("DEBUG 프로젝트:", project_name)
        print("DEBUG GitHub ID:", github_id)
        print("DEBUG Repo URL:", repo_url)

        if not repo_url:
            print("SKIP: Repo URL 없음")
            continue

        repo_url = repo_url.rstrip("/")

        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]

        prefix = "https://github.com/"

        if not repo_url.startswith(prefix):
            print("SKIP 잘못된 GitHub URL:", repo_url)
            continue

        repo_path = repo_url[len(prefix):]

        parts = repo_path.split("/")

        if len(parts) < 2:
            print("SKIP 잘못된 저장소:", repo_url)
            continue

        owner = parts[0]
        repo = parts[1]

        repositories.append({
            "github_id": github_id or owner,
            "project_name": project_name,
            "repo_path": f"{owner}/{repo}",
        })

    return repositories


def get_repository_info(repo_path):
    return request_json(
        f"https://api.github.com/repos/{repo_path}",
        headers=github_headers()
    )


def get_commits(repo_path, branch, per_page, page):
    url = (
        f"https://api.github.com/repos/{repo_path}/commits"
        f"?sha={quote(branch)}&per_page={per_page}&page={page}"
    )

    return request_json(url, headers=github_headers())


def get_all_commits(repo_path, branch):
    commits = []
    page = 1

    while True:
        batch = get_commits(
            repo_path,
            branch,
            per_page=BACKFILL_PAGE_SIZE,
            page=page,
        )
        if not batch:
            break

        commits.extend(batch)
        if len(batch) < BACKFILL_PAGE_SIZE:
            break

        page += 1

    return commits


def get_project_commits(repo_path, branch, sync_mode):
    cache_key = (repo_path, branch, sync_mode)
    if cache_key not in COMMIT_CACHE:
        if sync_mode == "backfill":
            COMMIT_CACHE[cache_key] = get_all_commits(repo_path, branch)
        else:
            COMMIT_CACHE[cache_key] = get_commits(
                repo_path,
                branch,
                per_page=INCREMENTAL_COMMIT_LIMIT,
                page=1,
            )

    return COMMIT_CACHE[cache_key]


def get_commit_detail(repo_path, sha):
    return request_json(
        f"https://api.github.com/repos/{repo_path}/commits/{sha}",
        headers=github_headers()
    )


def notion_has_sha(sha):
    url = f"https://api.notion.com/v1/data_sources/{COMMIT_DATA_SOURCE_ID}/query"

    payload = {
        "filter": {
            "property": "커밋SHA",
            "rich_text": {
                "equals": sha
            }
        }
    }

    result = request_json(
        url,
        method="POST",
        headers=notion_headers(),
        data=payload,
    )

    return len(result.get("results", [])) > 0


def is_meaningful_file(filename):
    name = filename.lower()

    ignore_patterns = [
        "library/",
        "temp/",
        "logs/",
        "obj/",
        "build/",
        "usersettings/",
    ]

    for pattern in ignore_patterns:
        if pattern in name:
            return False

    if name.endswith(".meta"):
        return False

    if name in [
        "readme.md",
        ".gitignore",
        ".gitattributes",
    ]:
        return False

    meaningful_extensions = [
        ".cs",
        ".py",
        ".js",
        ".ts",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".java",
        ".shader",
        ".compute",
        ".json",
        ".asmdef",
        ".unity",
        ".prefab",
        ".controller",
        ".anim",
        ".asset",
        ".mat",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".wav",
        ".mp3",
        ".ogg",
        ".fbx",
        ".blend",
    ]

    return any(name.endswith(ext) for ext in meaningful_extensions)


def analyze_commit(detail, message):
    stats = detail.get("stats", {})
    files = detail.get("files", [])

    additions = stats.get("additions", 0)
    deletions = stats.get("deletions", 0)

    changed_files = len(files)
    meaningful_file_count = 0
    meaningful_change = 0

    for file_info in files:
        filename = file_info.get("filename", "")

        if is_meaningful_file(filename):
            meaningful_file_count += 1

            meaningful_change += (
                file_info.get("additions", 0)
                + file_info.get("deletions", 0)
            )

    suspicious_score = 0

    if meaningful_file_count == 0:
        suspicious_score += 45

    if meaningful_change <= 2:
        suspicious_score += 35
    elif meaningful_change <= 10:
        suspicious_score += 15

    if changed_files == 1 and meaningful_change <= 5:
        suspicious_score += 15

    simple_messages = [
        "수정",
        "수정1",
        "수정2",
        "fix",
        "update",
        "test",
        "테스트",
        "변경",
    ]

    clean_message = message.strip().lower()

    if clean_message in simple_messages:
        suspicious_score += 10

    if len(clean_message) <= 2:
        suspicious_score += 10

    suspicious_score = min(suspicious_score, 100)

    if suspicious_score >= 70:
        judgment = "뻥의심"
    elif suspicious_score >= 35:
        judgment = "확인필요"
    else:
        judgment = "정상"

    return {
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
        "meaningful_change": meaningful_change,
        "meaningful_file_count": meaningful_file_count,
        "suspicious_score": suspicious_score,
        "judgment": judgment,
    }


def add_commit_to_notion(
    project_name,
    github_id,
    repo_path,
    branch,
    sha,
    message,
    commit_url,
    commit_date,
    analysis,
):
    url = "https://api.notion.com/v1/pages"

    payload = {
        "parent": {
            "type": "data_source_id",
            "data_source_id": COMMIT_DATA_SOURCE_ID,
        },
        "properties": {
            "커밋": {
                "title": [{
                    "text": {
                        "content": message[:2000]
                    }
                }]
            },
            "프로젝트명": {
                "rich_text": [{
                    "text": {
                        "content": project_name
                    }
                }]
            },
            "깃허브아이디": {
                "rich_text": [{
                    "text": {
                        "content": github_id
                    }
                }]
            },
            "저장소": {
                "rich_text": [{
                    "text": {
                        "content": repo_path
                    }
                }]
            },
            "브랜치": {
                "rich_text": [{
                    "text": {
                        "content": branch
                    }
                }]
            },
            "커밋SHA": {
                "rich_text": [{
                    "text": {
                        "content": sha
                    }
                }]
            },
            "커밋URL": {
                "url": commit_url
            },
            "날짜": {
                "date": {
                    "start": commit_date
                }
            },
            "변경파일수": {
                "number": analysis["changed_files"]
            },
            "추가라인": {
                "number": analysis["additions"]
            },
            "삭제라인": {
                "number": analysis["deletions"]
            },
            "실질변경량": {
                "number": analysis["meaningful_change"]
            },
            "의미파일수": {
                "number": analysis["meaningful_file_count"]
            },
            "의심점수": {
                "number": analysis["suspicious_score"]
            },
            "판정": {
                "select": {
                    "name": analysis["judgment"]
                }
            },
        },
    }

    request_json(
        url,
        method="POST",
        headers=notion_headers(),
        data=payload,
    )


def process_repository(project, sync_mode):
    repo_path = project["repo_path"]

    repo_info = get_repository_info(repo_path)
    branch = repo_info.get("default_branch", "main")

    print("")
    print("프로젝트:", project["project_name"])
    print("깃허브:", project["github_id"])
    print("저장소:", repo_path)
    print("브랜치:", branch)

    commits = get_project_commits(repo_path, branch, sync_mode)

    audit_entries = []
    expected_github = project["github_id"].casefold()

    for item in commits:
        sha = item.get("sha", "")

        commit = item.get("commit", {})
        message = commit.get("message", "").splitlines()[0]

        author = commit.get("author") or {}
        github_author = item.get("author") or {}
        github_author_login = github_author.get("login", "")
        commit_url = item.get("html_url", "")

        detail = get_commit_detail(repo_path, sha)
        analysis = analyze_commit(detail, message)

        if github_author_login:
            verification = "verified" if github_author_login.casefold() == expected_github else "mismatch"
        else:
            # The commit email is not linked to a visible GitHub account.
            verification = "unlinked"

        audit_entries.append({
            "projectName": project["project_name"] or project["github_id"],
            "repo": repo_path,
            "branch": branch,
            "sha": sha,
            "message": message,
            "url": commit_url,
            "date": author.get("date", ""),
            "expectedGithub": project["github_id"],
            "actualGithub": github_author_login or None,
            "gitAuthorName": author.get("name", ""),
            "gitAuthorEmail": author.get("email", ""),
            "verification": verification,
            "analysis": analysis,
        })

        print("AUDIT:", sha[:7], verification, github_author_login or "unlinked")

    return audit_entries


def write_commit_audit(entries):
    payload = {
        "updatedAt": datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime("%Y. %m. %d. %H:%M"),
        "verificationLabels": {
            "verified": "등록된 GitHub ID와 일치",
            "mismatch": "다른 GitHub 계정의 커밋",
            "unlinked": "GitHub 계정 연결을 확인할 수 없음",
        },
        "commits": entries,
    }
    with open("data/commit-audit.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_commit_audit_entries():
    audit_path = os.path.join("data", "commit-audit.json")
    if not os.path.exists(audit_path):
        return []

    with open(audit_path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    entries = payload.get("commits", [])
    if not isinstance(entries, list):
        raise ValueError("data/commit-audit.json must contain a commits array")

    return entries


def merge_audit_entries(existing_entries, incoming_entries):
    merged = {}

    for entry in [*existing_entries, *incoming_entries]:
        repo = entry.get("repo", "")
        sha = entry.get("sha", "")
        if repo and sha:
            merged[(repo, sha)] = entry

    return sorted(
        merged.values(),
        key=lambda entry: entry.get("date", ""),
        reverse=True,
    )

def parse_github_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def relative_time(value, now):
    parsed = parse_github_date(value)
    if not parsed:
        return "기록 없음"
    days = max(0, (now - parsed).days)
    return "오늘" if days == 0 else "어제" if days == 1 else f"{days}일 전"


def activity_status(value, now):
    parsed = parse_github_date(value)
    if not parsed:
        return "inactive"
    days = (now - parsed).days
    return "active" if days <= 3 else "watch" if days <= 7 else "inactive"


def make_dashboard_row(project, github_id, commits, now, source):
    repo_path = project["repo_path"]
    week_ago = now - timedelta(days=7)
    seoul_timezone = timezone(timedelta(hours=9))
    seoul_now = now.astimezone(seoul_timezone)
    semester_start_month = 1 if seoul_now.month <= 6 else 7
    semester_start = datetime(
        seoul_now.year,
        semester_start_month,
        1,
        tzinfo=seoul_timezone,
    )
    recent_week = [
        row for row in commits
        if parse_github_date(row["date"])
        and parse_github_date(row["date"]) >= week_ago
    ]
    semester_commits = [
        row for row in commits
        if parse_github_date(row["date"])
        and parse_github_date(row["date"]) >= semester_start
    ]
    active_days = len({row["date"][:10] for row in recent_week if row["date"]})
    weekly = []

    for index in range(6, -1, -1):
        start = now - timedelta(days=(index + 1) * 7)
        end = now - timedelta(days=index * 7)
        weekly.append(sum(
            1 for row in commits
            if parse_github_date(row["date"])
            and start <= parse_github_date(row["date"]) < end
        ))

    last_date = commits[0]["date"] if commits else ""
    is_registered_student = source == "registered"

    return {
        "name": (
            project["project_name"] or github_id
            if is_registered_student
            else f"{github_id} (실제 커밋 작성자)"
        ),
        "id": github_id,
        "team": repo_path.split("/")[0] if is_registered_student else project["project_name"],
        "github": github_id,
        "repo": repo_path,
        "commits": len(recent_week),
        "semesterCommits": len(semester_commits),
        "activeDays": active_days,
        "lastCommit": relative_time(last_date, now),
        "status": activity_status(last_date, now),
        "weekly": weekly,
        "recent": [
            {
                "message": row["message"],
                "time": relative_time(row["date"], now),
                "sha": row["sha"],
                "url": row["url"],
            }
            for row in commits[:5]
        ],
    }


def build_dashboard_data(projects, audit_entries):
    now = datetime.now(timezone.utc)
    entries_by_repo = {}
    rows = []

    for entry in audit_entries:
        entries_by_repo.setdefault(entry.get("repo", ""), []).append(entry)

    for project in projects:
        repo_path = project["repo_path"]
        expected_github = project["github_id"]
        expected_github_key = expected_github.casefold()
        commits = [
            {
                "date": entry.get("date", ""),
                "message": entry.get("message", ""),
                "sha": entry.get("sha", "")[:7],
                "url": entry.get("url", ""),
                "actualGithub": entry.get("actualGithub") or "",
            }
            for entry in entries_by_repo.get(repo_path, [])
        ]

        registered_commits = [
            row for row in commits
            if row["actualGithub"].casefold() == expected_github_key
        ]
        rows.append(make_dashboard_row(
            project,
            expected_github,
            registered_commits,
            now,
            source="registered",
        ))

        contributor_commits = {}
        contributor_display_ids = {}
        for row in commits:
            github_id = row["actualGithub"]
            if not github_id:
                continue

            github_key = github_id.casefold()
            if github_key == expected_github_key:
                continue

            contributor_commits.setdefault(github_key, []).append(row)
            contributor_display_ids.setdefault(github_key, github_id)

        for github_key, author_commits in contributor_commits.items():
            rows.append(make_dashboard_row(
                project,
                contributor_display_ids[github_key],
                author_commits,
                now,
                source="contributor",
            ))

    os.makedirs("data", exist_ok=True)
    payload = {
        "course": "Git 프로젝트 활동 현황",
        "notionUrl": "https://abaft-vibraphone-8f7.notion.site/Git-3c28655a72df80199dafc115fef9ddd4?pvs=74",
        "updatedAt": now.astimezone(timezone(timedelta(hours=9))).strftime("%Y. %m. %d. %H:%M"),
        "students": rows,
    }
    with open("data/students.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print("대시보드 조회 항목 수:", len(rows))
def main():
    sync_mode = os.environ.get("SYNC_MODE", "incremental").lower()
    force_backfill = os.environ.get("FORCE_BACKFILL", "false").lower() == "true"

    if sync_mode not in {"incremental", "backfill"}:
        raise ValueError("SYNC_MODE must be 'incremental' or 'backfill'")

    metadata = load_sync_metadata()
    if (
        sync_mode == "backfill"
        and metadata.get("backfill_completed_at")
        and not force_backfill
    ):
        print("소급 수집은 이미 완료되었습니다.")
        print("다시 실행하려면 FORCE_BACKFILL=true를 사용하세요.")
        return

    projects = get_project_repositories()
    existing_audit_entries = load_commit_audit_entries()
    audit_entries = []
    had_errors = False

    print("수집 모드:", sync_mode)
    print("활성 프로젝트 수:", len(projects))

    for project in projects:
        try:
            audit_entries.extend(process_repository(project, sync_mode))
        except Exception as error:
            had_errors = True
            print("ERROR:", project.get("repo_path"), str(error))

    audit_entries = merge_audit_entries(existing_audit_entries, audit_entries)
    write_commit_audit(audit_entries)
    build_dashboard_data(projects, audit_entries)

    if sync_mode == "backfill" and not had_errors:
        metadata["backfill_completed_at"] = datetime.now(timezone.utc).isoformat()
        save_sync_metadata(metadata)

if __name__ == "__main__":
    main()
