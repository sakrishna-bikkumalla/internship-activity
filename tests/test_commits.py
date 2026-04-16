"""
Tests for gitlab_compliance_checker.infrastructure.gitlab.commits.py

Covers all fixes made:
  - Timezone handling (aware vs naive timestamps)
  - Author matching via name, email, and username
  - Case-insensitive matching
  - Deduplication of commits across search terms and projects
  - Time-slot classification (Morning / Afternoon / Other)
  - Silent error handling per project
"""

from unittest.mock import MagicMock

from gitlab_compliance_checker.infrastructure.gitlab.commits import get_user_commits

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_commit(sha, author_name, author_email, created_at, title="Fix bug"):
    return {
        "id": sha,
        "short_id": sha[:8],
        "title": title,
        "author_name": author_name,
        "author_email": author_email,
        "created_at": created_at,
    }


def _make_project(pid, name="proj/example"):
    return {"id": pid, "name_with_namespace": name}


def _make_client(commits_per_call=None):
    """Return a mock GitLabClient whose _get_paginated returns `commits_per_call`."""
    client = MagicMock()
    if commits_per_call is None:
        client._get_paginated.return_value = []
    else:
        client._get_paginated.return_value = commits_per_call
    return client


# ---------------------------------------------------------------------------
# 1. Basic matching: author_name exact match
# ---------------------------------------------------------------------------


class TestAuthorNameMatching:
    def test_match_by_exact_name(self):
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1
        assert len(commits) == 1
        assert commits[0]["author_name"] == "Alice Dev"

    def test_no_match_different_name(self):
        commit = _make_commit("sha1", "Bob Smith", "bob@example.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 0
        assert len(commits) == 0

    def test_case_insensitive_name_match(self):
        """Matching should be case-insensitive (fix #3)."""
        commit = _make_commit("sha1", "alice dev", "alice@example.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1


# ---------------------------------------------------------------------------
# 2. Matching by email
# ---------------------------------------------------------------------------


class TestAuthorEmailMatching:
    def test_match_by_email_when_name_differs(self):
        """Even if the stored author_name differs, email match should still count."""
        commit = _make_commit("sha1", "Alice D.", "alice@example.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        # user.name won't match author_name in commit, but email will
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        # the api_params author=author_name returns this commit; validator checks email
        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1

    def test_case_insensitive_email_match(self):
        commit = _make_commit("sha1", "Alice Dev", "Alice@Example.COM", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Other Name", "email": "alice@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1


# ---------------------------------------------------------------------------
# 3. Matching by username (substring)
# ---------------------------------------------------------------------------


class TestUsernameMatching:
    def test_match_by_username_in_email(self):
        commit = _make_commit("sha1", "Alice", "alicedev@company.org", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Other Name", "email": "other@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1

    def test_no_match_by_fuzzy_username_in_name(self):
        commit = _make_commit("sha1", "alicedev (contractor)", "x@x.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}
    
        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])
    
        assert stats["total"] == 0

    def test_match_by_exact_username_in_name(self):
        commit = _make_commit("sha1", "alicedev", "x@x.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1


# ---------------------------------------------------------------------------
# 4. Timezone handling (fix #1 — the critical bug)
# ---------------------------------------------------------------------------


class TestTimezoneHandling:
    def test_utc_aware_timestamp_converted_to_ist(self):
        """A UTC-aware timestamp at 04:00 UTC → 09:30 IST → Morning slot."""
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T04:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, _, stats = get_user_commits(client, user, [_make_project(1)])

        assert len(commits) == 1
        assert commits[0]["slot"] == "Morning"
        assert stats["morning_commits"] == 1

    def test_ist_aware_timestamp_not_double_converted(self):
        """A +05:30 aware timestamp: 09:30 IST should still land in Morning slot."""
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T09:30:00+05:30")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, _, stats = get_user_commits(client, user, [_make_project(1)])

        assert commits[0]["slot"] == "Morning"
        assert stats["morning_commits"] == 1

    def test_naive_timestamp_assumed_utc(self):
        """A naive timestamp (no tz) at 04:00 → interpreted as UTC → 09:30 IST → Morning."""
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T04:00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, _, stats = get_user_commits(client, user, [_make_project(1)])

        assert commits[0]["slot"] == "Morning"

    def test_afternoon_slot_classification(self):
        """14:00 IST → Afternoon slot (08:30 UTC)."""
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T08:30:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, _, stats = get_user_commits(client, user, [_make_project(1)])

        assert commits[0]["slot"] == "Afternoon"
        assert stats["afternoon_commits"] == 1

    def test_other_slot_outside_both_windows(self):
        """Commit at 01:00 UTC = 06:30 IST → Other slot."""
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T01:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, _, stats = get_user_commits(client, user, [_make_project(1)])

        assert commits[0]["slot"] == "Other"
        assert stats["morning_commits"] == 0
        assert stats["afternoon_commits"] == 0


# ---------------------------------------------------------------------------
# 5. Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_same_sha_across_two_projects_counted_once(self):
        commit = _make_commit("sha_dup", "Alice Dev", "alice@example.com", "2024-01-15T10:00:00+00:00")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}
        projects = [_make_project(1, "proj/one"), _make_project(2, "proj/two")]

        all_commits, counts, stats = get_user_commits(client, user, projects)

        # total unique commits globally should be 1
        assert stats["total"] == 1
        # but each project still records it in its count
        assert counts[1] == 1
        assert counts[2] == 1

    def test_deduplication_within_single_project(self):
        """Commits returned twice (e.g. from two search terms) should be counted once per project."""
        commit = _make_commit("sha_dup", "Alice Dev", "alice@example.com", "2024-01-15T10:00:00+00:00")

        # Return same commit on every _get_paginated call (name search + username search)
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        all_commits, counts, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1
        assert counts[1] == 1


# ---------------------------------------------------------------------------
# 6. No projects
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_projects_returns_empty(self):
        client = _make_client()
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, counts, stats = get_user_commits(client, user, [])

        assert commits == []
        assert counts == {}
        assert stats["total"] == 0

    def test_project_api_error_is_skipped(self):
        """A project whose API call raises an exception should be skipped gracefully."""
        client = MagicMock()
        client._get_paginated.side_effect = Exception("Connection refused")

        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}
        projects = [_make_project(1)]

        # Should not raise, just skip
        commits, counts, stats = get_user_commits(client, user, projects)

        assert stats["total"] == 0
        assert commits == []

    def test_missing_email_field_still_matches_by_name(self):
        commit = _make_commit("sha1", "Alice Dev", None, "2024-01-15T10:00:00+00:00")
        commit["author_email"] = None
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": None, "username": "alicedev"}

        commits, _, stats = get_user_commits(client, user, [_make_project(1)])

        assert stats["total"] == 1

    def test_date_and_time_fields_populated(self):
        commit = _make_commit("sha1", "Alice Dev", "alice@example.com", "2024-01-15T09:30:00+05:30")
        client = _make_client([commit])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        commits, _, _ = get_user_commits(client, user, [_make_project(1)])

        assert commits[0]["date"] == "2024-01-15"
        assert commits[0]["time"] != "N/A"

    def test_since_until_passed_to_api(self):
        """since/until params should be forwarded to _get_paginated."""
        client = _make_client([])
        user = {"name": "Alice Dev", "email": "alice@example.com", "username": "alicedev"}

        get_user_commits(
            client,
            user,
            [_make_project(1)],
            since="2024-01-01T00:00:00Z",
            until="2024-01-31T23:59:59Z",
        )

        # Check that at least one call included the since/until params
        called_params = [
            call.kwargs.get("params", {}) or call.args[1] if call.args else {}
            for call in client._get_paginated.call_args_list
        ]
        assert any("since" in str(p) for p in called_params)
        assert any("until" in str(p) for p in called_params)

    def test_search_by_email_only(self):
        """If name and username are missing, should use email for search."""
        commit = _make_commit("sha1", "Alice", "alice@test.com", "2024-01-15T10:00:00Z")
        client = _make_client([commit])
        user = {"email": "alice@test.com"}  # No name or username

        commits, _, _ = get_user_commits(client, user, [_make_project(1)])
        # After removing API-side author filter, email matching happens client-side
        # The commit should still be found via flexible email matching
        assert len(commits) == 1
        assert commits[0]["author_name"] == "Alice"

    def test_invalid_date_format_handled(self):
        """Commits with weird dates should return N/A slot."""
        commit = _make_commit("sha1", "Alice", "a@b.com", "not-a-date")
        client = _make_client([commit])
        user = {"name": "Alice"}

        commits, _, _ = get_user_commits(client, user, [_make_project(1)])
        assert commits[0]["slot"] == "N/A"
        assert commits[0]["time"] == "N/A"
