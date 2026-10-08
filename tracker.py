import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from urllib.parse import quote

NOTION_TOKEN = os.environ["NOTION_TOKEN"]

COMMIT_DATA_SOURCE_ID = "3c28655a-72df-8076-a7aa-000b7d2948d4"
PROJECT_DATA_SOURCE_ID = "3c28655a-72df-8061-8782-000ba17e1ab9"

NOTION_VERSION = "2025-09-03"
COMMIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "commits.json")
ARCHIVE_META_PATH = os.path.join(os.path.dirname(__file__), "archive-meta.json")
INCREMENTAL_COMMIT_LIMIT = 50
BACKFILL_PAGE_SIZE = 100


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

    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    return headers


def load_commit_log():
    if not os.path.exists(COMMIT_LOG_PATH):
        return []

    with open(COMMIT_LOG_PATH, "r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("commits.json must contain a JSON array")

    return records


def save_commit_log(records):
    with open(COMMIT_LOG_PATH, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_known_shas(records):
    return {record.get("sha") for record in records if record.get("sha")}



def load_archive_metadata():
    if not os.path.exists(ARCHIVE_META_PATH):
        return {}

    with open(ARCHIVE_META_PATH, "r", encoding="utf-8") as file:
        metadata = json.load(file)

    if not isinstance(metadata, dict):
        raise ValueError("archive-meta.json must contain a JSON object")

    return metadata


def save_archive_metadata(metadata):
    with open(ARCHIVE_META_PATH, "w", encoding="utf-8") as file:
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


def process_repository(project, known_shas, records, sync_mode):
    repo_path = project["repo_path"]

    repo_info = get_repository_info(repo_path)
    branch = repo_info.get("default_branch", "main")

    print("")
    print("프로젝트:", project["project_name"])
    print("깃허브:", project["github_id"])
    print("저장소:", repo_path)
    print("브랜치:", branch)

    if sync_mode == "backfill":
        commits = get_all_commits(repo_path, branch)
        print("소급 수집 대상 커밋 수:", len(commits))
    else:
        commits = get_commits(
            repo_path,
            branch,
            per_page=INCREMENTAL_COMMIT_LIMIT,
            page=1,
        )
        print("증분 수집 대상 커밋 수:", len(commits))

    for item in reversed(commits):
        sha = item.get("sha", "")

        github_author = item.get("author") or {}
        commit_github_id = github_author.get("login", "")
        commit = item.get("commit", {})
        message = commit.get("message", "").splitlines()[0]

        author = commit.get("author") or {}
        commit_date = author.get("date", "")

        commit_url = item.get("html_url", "")

        # Attribute each record to the actual GitHub account that made the commit.
        # Do not assign commits without a mapped GitHub ID to another student.
        if not commit_github_id:
            print("SKIP: GitHub ID 없음:", sha[:7], message)
            continue

        if sha in known_shas:
            print("SKIP:", sha[:7], message)
            continue

        detail = get_commit_detail(repo_path, sha)
        analysis = analyze_commit(detail, message)

        records.append({
            "project_name": project["project_name"],
            "github_id": commit_github_id,
            "repo_path": repo_path,
            "branch": branch,
            "sha": sha,
            "message": message,
            "commit_url": commit_url,
            "commit_date": commit_date,
            "changed_files": analysis["changed_files"],
            "additions": analysis["additions"],
            "deletions": analysis["deletions"],
            "meaningful_change": analysis["meaningful_change"],
            "meaningful_file_count": analysis["meaningful_file_count"],
            "suspicious_score": analysis["suspicious_score"],
            "judgment": analysis["judgment"],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        known_shas.add(sha)

        print(
            "ADD:",
            sha[:7],
            message,
            "/",
            analysis["judgment"],
            "/ 점수:",
            analysis["suspicious_score"]
        )


def main():
    sync_mode = os.environ.get("SYNC_MODE", "incremental").lower()
    force_backfill = os.environ.get("FORCE_BACKFILL", "false").lower() == "true"

    if sync_mode not in {"incremental", "backfill"}:
        raise ValueError("SYNC_MODE must be 'incremental' or 'backfill'")

    metadata = load_archive_metadata()
    if (
        sync_mode == "backfill"
        and metadata.get("backfill_completed_at")
        and not force_backfill
    ):
        print("소급 수집은 이미 완료되었습니다.")
        print("다시 실행하려면 FORCE_BACKFILL=true를 사용하세요.")
        return

    records = load_commit_log()
    known_shas = get_known_shas(records)
    projects = get_project_repositories()
    had_errors = False

    print("수집 모드:", sync_mode)
    print("활성 프로젝트 수:", len(projects))

    for project in projects:
        try:
            process_repository(project, known_shas, records, sync_mode)

        except Exception as e:
            had_errors = True
            print(
                "ERROR:",
                project.get("repo_path"),
                str(e)
            )

    save_commit_log(records)

    if sync_mode == "backfill" and not had_errors:
        metadata["backfill_completed_at"] = datetime.now(timezone.utc).isoformat()
        save_archive_metadata(metadata)

    print("저장된 커밋 수:", len(records))


if __name__ == "__main__":
    main()
