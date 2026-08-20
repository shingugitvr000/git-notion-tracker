import json
import os
import urllib.request
import urllib.error


# =========================================================
# 설정
# =========================================================

NOTION_TOKEN = os.environ["NOTION_TOKEN"]

# CommitDB의 Data Source ID
DATA_SOURCE_ID = "3c28655a-72df-80fb-9fb4-000b388214b4"

# 테스트 대상 GitHub 저장소
# 나중에는 이 부분을 Notion에서 자동으로 읽게 바꿀 예정
REPOSITORIES = [
    "shingugitvr000/GameJam2026"
]


# =========================================================
# API Headers
# =========================================================

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json",
}

GITHUB_HEADERS = {
    "User-Agent": "git-notion-tracker"
}


# =========================================================
# 공통 HTTP 요청 함수
# =========================================================

def request_json(url, method="GET", headers=None, body=None):
    data = None

    if body is not None:
        data = json.dumps(body).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers or {}
    )

    try:
        with urllib.request.urlopen(request) as response:
            text = response.read().decode("utf-8")

            if not text:
                return {}

            return json.loads(text)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")

        print("========================================")
        print("HTTP ERROR")
        print("STATUS:", e.code)
        print("URL:", url)
        print("BODY:")
        print(error_body)
        print("========================================")

        raise


# =========================================================
# GitHub
# =========================================================

def get_repository_info(repo):
    url = f"https://api.github.com/repos/{repo}"

    return request_json(
        url,
        headers=GITHUB_HEADERS
    )


def get_commits(repo, branch):
    url = (
        f"https://api.github.com/repos/{repo}/commits"
        f"?sha={branch}&per_page=10"
    )

    return request_json(
        url,
        headers=GITHUB_HEADERS
    )


# =========================================================
# Notion 중복 SHA 검사
# =========================================================

def notion_has_sha(sha):
    body = {
        "filter": {
            "property": "Commit SHA",
            "rich_text": {
                "equals": sha
            }
        },
        "page_size": 1
    }

    url = (
        f"https://api.notion.com/v1/"
        f"data_sources/{DATA_SOURCE_ID}/query"
    )

    result = request_json(
        url,
        method="POST",
        headers=NOTION_HEADERS,
        body=body
    )

    return len(result.get("results", [])) > 0


# =========================================================
# Notion에 Commit 추가
# =========================================================

def add_commit_to_notion(repo, branch, commit):

    sha = commit["sha"]

    commit_data = commit["commit"]

    message = commit_data.get("message", "")

    commit_url = commit.get("html_url", "")

    author_date = (
        commit_data
        .get("author", {})
        .get("date", "")
    )

    # GitHub 계정과 연결된 commit이면 login 사용
    github_id = ""

    if commit.get("author"):
        github_id = commit["author"].get("login", "")

    # GitHub 계정 정보가 없는 commit의 경우
    # commit author name 사용
    if not github_id:
        github_id = (
            commit_data
            .get("author", {})
            .get("name", "")
        )


    body = {
        "parent": {
            "type": "data_source_id",
            "data_source_id": DATA_SOURCE_ID
        },

        "properties": {

            "커밋": {
                "title": [
                    {
                        "text": {
                            "content": message[:2000]
                        }
                    }
                ]
            },

            "GitHub ID": {
                "rich_text": [
                    {
                        "text": {
                            "content": github_id[:2000]
                        }
                    }
                ]
            },

            "Repository": {
                "rich_text": [
                    {
                        "text": {
                            "content": repo
                        }
                    }
                ]
            },

            "Branch": {
                "rich_text": [
                    {
                        "text": {
                            "content": branch
                        }
                    }
                ]
            },

            "Commit SHA": {
                "rich_text": [
                    {
                        "text": {
                            "content": sha
                        }
                    }
                ]
            },

            "Commit URL": {
                "url": commit_url
            },

            "날짜": {
                "date": {
                    "start": author_date
                }
            }
        }
    }

    request_json(
        "https://api.notion.com/v1/pages",
        method="POST",
        headers=NOTION_HEADERS,
        body=body
    )

    first_line = message.splitlines()[0]

    print(
        "ADD:",
        repo,
        branch,
        sha[:7],
        first_line
    )


# =========================================================
# Repository 처리
# =========================================================

def process_repository(repo):

    print()
    print("==========================================")
    print("CHECK:", repo)

    repo_info = get_repository_info(repo)

    default_branch = repo_info.get(
        "default_branch",
        "main"
    )

    print("BRANCH:", default_branch)

    commits = get_commits(
        repo,
        default_branch
    )

    print("COMMITS:", len(commits))


    # 오래된 커밋부터 처리
    for commit in reversed(commits):

        sha = commit["sha"]

        message = (
            commit["commit"]
            .get("message", "")
            .splitlines()[0]
        )

        print()
        print(
            "CHECK SHA:",
            sha[:7],
            message
        )


        # 이미 Notion에 있으면 건너뜀
        if notion_has_sha(sha):

            print(
                "SKIP:",
                sha[:7]
            )

            continue


        # 없는 Commit만 추가
        add_commit_to_notion(
            repo,
            default_branch,
            commit
        )


# =========================================================
# Main
# =========================================================

def main():

    print()
    print("==========================================")
    print("Git → Notion Tracker START")
    print("==========================================")


    for repo in REPOSITORIES:

        try:

            process_repository(repo)

        except Exception as e:

            print()
            print("ERROR Repository:", repo)
            print("ERROR:", str(e))

            raise


    print()
    print("==========================================")
    print("Git → Notion Tracker COMPLETE")
    print("==========================================")


if __name__ == "__main__":
    main()