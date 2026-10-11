import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("NOTION_TOKEN", "test-token")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
tracker = importlib.import_module("tracker")


class BackfillTests(unittest.TestCase):
    def setUp(self):
        tracker.COMMIT_CACHE.clear()

    def test_get_all_commits_reads_past_first_hundred(self):
        pages = {
            1: [{"sha": f"sha-{index}"} for index in range(100)],
            2: [{"sha": f"sha-{index}"} for index in range(100, 137)],
        }

        with patch.object(
            tracker,
            "get_commits",
            side_effect=lambda _repo, _branch, per_page, page: pages.get(page, []),
        ):
            commits = tracker.get_all_commits("owner/repo", "main")

        self.assertEqual(137, len(commits))

    def test_existing_sha_is_reused_without_detail_request(self):
        project = {
            "repo_path": "owner/repo",
            "project_name": "project",
            "github_id": "student",
        }
        existing = {
            ("owner/repo", "known-sha"): {
                "repo": "owner/repo",
                "sha": "known-sha",
                "date": "2026-10-01T00:00:00Z",
            }
        }
        listed = [{"sha": "known-sha", "commit": {"author": {"date": "2026-10-01T00:00:00Z"}}}]

        with patch.object(tracker, "get_repository_info", return_value={"default_branch": "main"}), \
             patch.object(tracker, "get_project_commits", return_value=listed), \
             patch.object(tracker, "get_commit_detail") as detail:
            entries, had_errors = tracker.process_repository(project, "backfill", existing)

        self.assertEqual([existing[("owner/repo", "known-sha")]], entries)
        self.assertFalse(had_errors)
        detail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
