import pytest

from tests.cmd_helpers import assert_stdout, assert_stderr


class TestBranchWithChainOfCommits:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        messages = ["first", "second", "third"]
        for msg in messages:
            write_file("file.txt", msg)
            legit_cmd("add", ".")
            commit(msg)

    def test_it_creates_a_branch_pointing_at_head(self, repo, legit_cmd):
        head_sha = repo.refs.read_head()
        _ = legit_cmd("branch", "topic")
        assert repo.refs.read_ref("topic") == head_sha

    def test_it_fails_for_invalid_branch_names(self, legit_cmd):
        _, _, _, stderr = legit_cmd("branch", "^")
        assert_stderr(stderr, "fatal: '^' is not a valid branch name.\n")

    def test_it_fails_for_existing_branch_names(self, legit_cmd):
        _ = legit_cmd("branch", "topic")
        _, _, _, stderr = legit_cmd("branch", "topic")
        assert_stderr(stderr, "fatal: A branch named 'topic' already exists.\n")

    def test_it_creates_a_branch_pointing_at_heads_parent(self, repo, legit_cmd):
        head_sha = repo.refs.read_head()
        head_commit = repo.database.load(head_sha)
        parent_sha = head_commit.parent
        _ = legit_cmd("branch", "topic", "HEAD^")
        assert repo.refs.read_ref("topic") == parent_sha

    def test_it_creates_a_branch_pointing_at_heads_grandparent(self, repo, legit_cmd):
        head_sha = repo.refs.read_head()
        head_commit = repo.database.load(head_sha)
        parent_commit = repo.database.load(head_commit.parent)
        grandparent_sha = parent_commit.parent
        _ = legit_cmd("branch", "topic", "@~2")
        assert repo.refs.read_ref("topic") == grandparent_sha

    def test_it_creates_a_branch_relative_to_another_one(self, repo, legit_cmd, resolve_revision):
        _ = legit_cmd("branch", "topic", "@~1")
        _ = legit_cmd("branch", "another", "topic^")
        
        assert repo.refs.read_ref("another") == resolve_revision("HEAD~2")

    def test_it_creates_a_branch_from_short_commit_id(self, repo, legit_cmd, resolve_revision):
        commit_id = resolve_revision("@~2")
        _ = legit_cmd("branch", "topic", repo.database.short_oid(commit_id))
        assert repo.refs.read_ref("topic") == commit_id

    def test_it_fails_for_invalid_revisions(self, legit_cmd):
        *_, stderr = legit_cmd("branch", "topic", "^")
        assert_stderr(stderr, "fatal: Not a valid object name: '^'.\n")

    def test_it_fails_for_invalid_refs(self, legit_cmd):
        *_, stderr = legit_cmd("branch", "topic", "no-such-branch")
        assert_stderr(stderr, "fatal: Not a valid object name: 'no-such-branch'.\n")

    def test_it_fails_for_invalid_parents(self, legit_cmd):
        *_, stderr = legit_cmd("branch", "topic", "HEAD^^^^")
        assert_stderr(stderr, "fatal: Not a valid object name: 'HEAD^^^^'.\n")

    def test_it_fails_for_invalid_ancestors(self, legit_cmd):
        *_, stderr = legit_cmd("branch", "topic", "HEAD~50")
        assert_stderr(stderr, "fatal: Not a valid object name: 'HEAD~50'.\n")

    def test_it_fails_for_revisions_that_are_not_commits(self, repo, legit_cmd):
        tree_id = repo.database.load(repo.refs.read_head()).tree
        *_, stderr = legit_cmd("branch", "topic", tree_id)
        expected = (
            f"error: object {tree_id} is a tree, not a commit\n"
            f"fatal: Not a valid object name: '{tree_id}'.\n"
        )
        assert_stderr(stderr, expected)

    def test_it_fails_for_parents_of_revisions_that_are_not_commits(self, repo, legit_cmd):
        tree_id = repo.database.load(repo.refs.read_head()).tree
        spec = f"{tree_id}^^"
        *_, stderr = legit_cmd("branch", "topic", spec)
        expected = (
            f"error: object {tree_id} is a tree, not a commit\n"
            f"fatal: Not a valid object name: '{spec}'.\n"
        )
        assert_stderr(stderr, expected)

    def test_it_lists_existing_branches(self, legit_cmd):
        legit_cmd("branch", "new-feature")
        *_, stdout, _ = legit_cmd("branch")
        assert_stdout(stdout, "* master\n  new-feature\n")

    def test_it_lists_existing_branches_with_verbose_info(self, repo, legit_cmd, load_commit):
        a = load_commit("@^")
        b = load_commit("@")
        *_, = legit_cmd("branch", "new-feature", "@^")
        *_, stdout, _ = legit_cmd("branch", "--verbose")
        expected = (
            f"* master      {repo.database.short_oid(b.oid)} third\n"
            f"  new-feature {repo.database.short_oid(a.oid)} second\n"
        )
        assert_stdout(stdout, expected)

    def test_it_deletes_a_branch(self, repo, legit_cmd):
        head = repo.refs.read_head()
        _ = legit_cmd("branch", "bug-fix")
        *_, stdout, _ = legit_cmd("branch", "--delete", "bug-fix")

        assert_stdout(stdout, f"Deleted branch 'bug-fix' (was {repo.database.short_oid(head)}).\n")

        names = [r.short_name for r in repo.refs.list_branches()]
        assert "bug-fix" not in names

    def test_it_fails_to_delete_nonexistent_branch(self, legit_cmd):
        cmd, *_, stderr = legit_cmd("branch", "--delete", "no-such-branch")
        assert cmd.status == 1
        assert_stderr(stderr, "error: branch 'no-such-branch' not found.\n")

