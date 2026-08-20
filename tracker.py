import os
import json
import urllib.request
import urllib.error

NOTION_TOKEN = os.environ["NOTION_TOKEN"]

COMMIT_DATA_SOURCE_ID = "3c28655a-72df-8076-a7aa-000b7d2948d4"
PROJECT_DATA_SOURCE_ID = "3c28655a-72df-8061-8782-000ba17e1ab9"

NOTION_VERSION = "2025-09-03"


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

            if not body:
                return {}

            return json.loads(body)

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print("HTTP ERROR:", e.code)
        print("BODY:", body)
        raise


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_project_repositories():
    url = (
        f"https://api.notion.com/v1/data_sources/"
        f"{PROJECT_DATA_SOURCE_ID}/query"
    )

    payload = {
        "filter": {
            "property": "사용 여부",
            "checkbox": {
                "equals": True
            }
        }
    }

    result = request_json(
        url,
        method="POST",
        headers=notion_headers(),
        data=payload,
    )

    repositories = []

    for page in result.get("results", []):
        props = page.get("properties", {})

        github_id = ""
        repo_url = ""
        project_name = ""

        if "GitHub ID" in props:
            rich_text = props["GitHub ID"].get("rich_text", [])
            if rich_text:
                github_id = rich_text[0].get("plain_text", "")

        if "Repo URL" in props:
            repo_url = props["Repo URL"].get("url") or ""

        if "프로젝트명" in props:
            title = props["프로젝트명"].get("title", [])
            if title:
                project_name = title[0].get("plain_text", "")

        if not repo_url:
            continue

        repo_url = repo_url.rstrip("/")

        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]

        prefix = "https://github.com/"

        if not repo_url.startswith(prefix):
            print("SKIP invalid GitHub URL:", repo_url)
            continue

        repo_path = repo_url[len(prefix):]

        parts = repo_path.split("/")

        if len(parts) < 2:
            print("SKIP invalid repository:", repo_url)
            continue

        owner = parts[0]
        repo = parts[1]

        repositories.append(
            {
                "github_id": github_id or owner,
                "project_name": project_name,
                "repo_path": f"{owner}/{repo}",
                "repo_url": repo_url,
            }
        )

    return repositories


def get_repository_info(repo_path):
    url = f"https://api.github.com/repos/{repo_path}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "git-notion-tracker",
    }

    return request_json(url, headers=headers)


def get_commits(repo_path, branch):
    url = (
        f"https://api.github.com/repos/{repo_path}/commits"
        f"?sha={branch}&per_page=10"
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "git-notion-tracker",
    }

    return request_json(url, headers=headers)


def notion_has_sha(sha):
    url = (
        f"https://api.notion.com/v1/data_sources/"
        f"{COMMIT_DATA_SOURCE_ID}/query"
    )

    payload = {
        "filter": {
            "property": "Commit SHA",
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


def add_commit_to_notion(
    github_id,
    repo_path,
    branch,
    sha,
    message,
    commit_url,
    commit_date,
):
    url = "https://api.notion.com/v1/pages"

    payload = {
        "parent": {
            "type": "data_source_id",
            "data_source_id": COMMIT_DATA_SOURCE_ID,
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
                            "content": repo_path
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
                    "start": commit_date
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


def process_repository(project):
    repo_path = project["repo_path"]
    github_id = project["github_id"]

    print("")
    print("================================")
    print("PROJECT:", project["project_name"])
    print("GITHUB ID:", github_id)
    print("REPOSITORY:", repo_path)
    print("================================")

    repo_info = get_repository_info(repo_path)

    branch = repo_info.get("default_branch", "main")

    print("DEFAULT BRANCH:", branch)

    commits = get_commits(repo_path, branch)

    for item in reversed(commits):
        sha = item.get("sha", "")

        commit = item.get("commit", {})
        message = commit.get("message", "").splitlines()[0]

        author = commit.get("author") or {}
        commit_date = author.get("date", "")

        commit_url = item.get("html_url", "")

        print("CHECK SHA:", sha[:7], message)

        if notion_has_sha(sha):
            print("SKIP:", sha[:7])
            continue

        add_commit_to_notion(
            github_id=github_id,
            repo_path=repo_path,
            branch=branch,
            sha=sha,
            message=message,
            commit_url=commit_url,
            commit_date=commit_date,
        )

        print(
            "ADD:",
            repo_path,
            branch,
            sha[:7],
            message,
        )


def main():
    projects = get_project_repositories()

    print("ACTIVE PROJECTS:", len(projects))

    if not projects:
        print("No active projects found.")
        return

    for project in projects:
        try:
            process_repository(project)

        except Exception as e:
            print(
                "ERROR:",
                project.get("repo_path"),
                str(e),
            )


if __name__ == "__main__":
    main()