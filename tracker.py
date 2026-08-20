import json
import os
import urllib.request
import urllib.parse

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# 테스트용: 나중에는 Notion 프로젝트 DB에서 자동으로 읽게 바꿀 예정
REPOSITORIES = [
    "shingugitvr000/GameJam2026"
]

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

GITHUB_HEADERS = {
    "User-Agent": "git-notion-tracker"
}


def request_json(url, method="GET", headers=None, body=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers or {}
    )

    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def get_commits(repo):
    url = f"https://api.github.com/repos/{repo}/commits?per_page=10"
    return request_json(url, headers=GITHUB_HEADERS)


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

    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"

    result = request_json(
        url,
        method="POST",
        headers=NOTION_HEADERS,
        body=body
    )

    return len(result.get("results", [])) > 0


def add_commit_to_notion(repo, commit):
    github_id = ""

    if commit.get("author"):
        github_id = commit["author"].get("login", "")

    if not github_id:
        github_id = commit["commit"]["author"].get("name", "")

    message = commit["commit"]["message"]
    sha = commit["sha"]
    url = commit["html_url"]
    date = commit["commit"]["author"]["date"]

    body = {
        "parent": {
            "database_id": DATABASE_ID
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
                            "content": github_id
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
                            "content": "default"
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
                "url": url
            },
            "날짜": {
                "date": {
                    "start": date
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

    print("ADD:", repo, sha[:7], message.splitlines()[0])


def main():
    for repo in REPOSITORIES:
        print("CHECK:", repo)

        commits = get_commits(repo)

        # 오래된 것부터 넣으면 Notion 순서가 자연스러움
        for commit in reversed(commits):
            sha = commit["sha"]

            if notion_has_sha(sha):
                print("SKIP:", sha[:7])
                continue

            add_commit_to_notion(repo, commit)


if __name__ == "__main__":
    main()