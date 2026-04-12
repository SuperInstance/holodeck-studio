"""Tests for seed_world — repo-to-room conversion."""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestRepoToRoom:
    def test_python_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({
            "name": "test-repo",
            "description": "A test Python project",
            "language": "Python"
        })
        assert room["name"] == "Test Repo"
        assert "Python" in room["description"]
        assert "A test Python project" in room["description"]
        assert room["exits"] == {"tavern": "tavern"}

    def test_go_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "flux-vm", "language": "Go"})
        assert "Go" in room["description"]

    def test_rust_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "edge-encoder", "language": "Rust"})
        assert "Rust" in room["description"]

    def test_c_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "bare-metal", "language": "C"})
        assert "bare-metal" in room["description"]

    def test_typescript_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "web-ui", "language": "TypeScript"})
        assert "TypeScript" in room["description"]

    def test_javascript_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "api-server", "language": "JavaScript"})
        assert "event-driven" in room["description"]

    def test_zig_repo(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "zig-tool", "language": "Zig"})
        assert "Zig" in room["description"]

    def test_unknown_language(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "mystery", "language": "COBOL"})
        assert "fully operational" in room["description"]

    def test_missing_description(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "no-desc", "language": "Python", "description": ""})
        assert "Python" in room["description"]

    def test_underscore_name(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "my_awesome_repo", "language": "Python"})
        assert room["name"] == "My Awesome Repo"

    def test_room_structure(self):
        from seed_world import repo_to_room
        room = repo_to_room({"name": "test", "language": "Python"})
        assert "notes" in room
        assert "items" in room
        assert "projections" in room
        assert room["notes"] == []
        assert room["items"] == []


class TestGetRepos:
    @patch("seed_world.urllib.request.urlopen")
    def test_get_repos_success(self, mock_urlopen):
        from seed_world import get_repos
        page1 = json.dumps([
            {"name": "repo1", "description": "d1", "language": "Python", "topics": []},
            {"name": "repo2", "description": "d2", "language": "Go", "topics": ["flux"]},
        ]).encode()
        page_empty = json.dumps([]).encode()

        call_count = [0]
        def make_resp(data):
            mock = MagicMock()
            mock.read.return_value = data
            mock.__enter__ = lambda s: mock
            mock.__exit__ = lambda s, *a: None
            return mock

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_resp(page1)
            return make_resp(page_empty)

        mock_urlopen.side_effect = side_effect

        repos = get_repos("TestOrg", limit=10)
        assert len(repos) == 2
        assert repos[0]["name"] == "repo1"
        assert repos[1]["topics"] == ["flux"]

    @patch("seed_world.urllib.request.urlopen")
    def test_get_repos_error_handling(self, mock_urlopen):
        from seed_world import get_repos
        mock_urlopen.side_effect = Exception("API error")
        repos = get_repos("TestOrg")
        assert repos == []

    @patch("seed_world.urllib.request.urlopen")
    def test_get_repos_empty_response(self, mock_urlopen):
        from seed_world import get_repos
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([]).encode()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = lambda s, *a: None
        # First call returns empty, second call also empty (pagination stops)
        mock_urlopen.return_value = mock_resp
        repos = get_repos("TestOrg")
        assert repos == []

    @patch("seed_world.urllib.request.urlopen")
    def test_get_repos_respects_limit(self, mock_urlopen):
        from seed_world import get_repos
        repos_data = [{"name": f"repo{i}", "description": f"d{i}",
                       "language": "Python", "topics": []} for i in range(200)]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(repos_data).encode()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_resp
        repos = get_repos("TestOrg", limit=5)
        assert len(repos) == 5

    @patch("seed_world.urllib.request.urlopen")
    def test_get_repos_null_description(self, mock_urlopen):
        from seed_world import get_repos
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {"name": "repo1", "description": None, "language": None, "topics": []}
        ]).encode()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_resp
        repos = get_repos("TestOrg")
        assert repos[0]["description"] == ""
        assert repos[0]["language"] == "unknown"
