import pytest

@pytest.fixture
def commit_chain(write_file, legit_cmd, commit):
    """
    Create a linear chain of three commits with messages "first", "second", "third".
    """
    messages = ["first", "second", "third"]
    for msg in messages:
        write_file("file.txt", msg)
        legit_cmd("add", ".")
        commit(msg)
    return messages

class TestBranchWithChainOfCommits:
    def test_creates_branch_pointing_at_head(self, repo, legit_cmd, commit_chain):
        # HEAD is at the "third" commit
        head_sha = repo.refs.read_head()
        cmd, stdin, stdout, stderr = legit_cmd("branch", "topic")
        # new branch 'topic' should point to the same SHA
        assert repo.refs.read_ref("topic") == head_sha

    def test_fails_for_invalid_branch_names(self, legit_cmd):
        _, _, _, stderr = legit_cmd("branch", "^")
        assert stderr.getvalue() == "fatal: '^' is not a valid branch name.\n"

    def test_fails_for_existing_branch_names(self, repo, legit_cmd, commit_chain):
        legit_cmd("branch", "topic")
        _, _, _, stderr = legit_cmd("branch", "topic")
        assert stderr.getvalue() == "fatal: A branch named 'topic' already exists.\n"

    def test_creates_branch_pointing_at_heads_parent(self, repo, legit_cmd, commit_chain):
        # HEAD → "third", its parent → "second"
        head_sha = repo.refs.read_head()
        head_commit = repo.database.load(head_sha)
        parent_sha = head_commit.parent
        legit_cmd("branch", "topic", "HEAD^")
        assert repo.refs.read_ref("topic") == parent_sha

    def test_creates_branch_pointing_at_heads_grandparent(self, repo, legit_cmd, commit_chain):
        # HEAD → third → second → first
        head_sha = repo.refs.read_head()
        head_commit = repo.database.load(head_sha)
        parent_commit = repo.database.load(head_commit.parent)
        grandparent_sha = parent_commit.parent
        legit_cmd("branch", "topic", "HEAD~2")
        assert repo.refs.read_ref("topic") == grandparent_sha

    def test_creates_branch_relative_to_another_one(self, repo, legit_cmd, commit_chain):
        # topic → HEAD~1 (second); another → topic^ (first)
        head_sha = repo.refs.read_head()
        head_commit = repo.database.load(head_sha)
        grandparent_sha = repo.database.load(head_commit.parent).parent

        legit_cmd("branch", "topic", "HEAD~1")
        legit_cmd("branch", "another", "topic^")
        assert repo.refs.read_ref("another") == grandparent_sha

    def test_creates_branch_from_short_commit_id(self, repo, legit_cmd, commit_chain):
        # compute the SHA of HEAD~2 (the "first" commit)
        head_sha = repo.refs.read_head()
        first_sha = repo.database.load(repo.database.load(head_sha).parent).parent
        short = repo.database.short_oid(first_sha)

        legit_cmd("branch", "topic", short)
        assert repo.refs.read_ref("topic") == first_sha

    def test_fails_for_invalid_revisions(self, legit_cmd):
        _, _, _, stderr = legit_cmd("branch", "topic", "^")
        assert stderr.getvalue() == "fatal: Not a valid object name: '^'.\n"

    def test_fails_for_invalid_refs(self, legit_cmd):
        _, _, _, stderr = legit_cmd("branch", "topic", "no-such-branch")
        assert stderr.getvalue() == "fatal: Not a valid object name: 'no-such-branch'.\n"

    def test_fails_for_invalid_parents(self, legit_cmd):
        _, _, _, stderr = legit_cmd("branch", "topic", "HEAD^^^^")
        assert stderr.getvalue() == "fatal: Not a valid object name: 'HEAD^^^^'.\n"

    def test_fails_for_invalid_ancestors(self, legit_cmd):
        _, _, _, stderr = legit_cmd("branch", "topic", "HEAD~50")
        assert stderr.getvalue() == "fatal: Not a valid object name: 'HEAD~50'.\n"

    def test_fails_for_revisions_that_are_not_commits(self, repo, legit_cmd, commit_chain):
        head_sha = repo.refs.read_head()
        tree_id = repo.database.load(head_sha).tree

        _, _, _, stderr = legit_cmd("branch", "topic", tree_id)
        expected = (
            f"error: object {tree_id} is a tree, not a commit\n"
            f"fatal: Not a valid object name: '{tree_id}'.\n"
        )
        assert stderr.getvalue() == expected

    def test_fails_for_parents_of_revisions_that_are_not_commits(self, repo, legit_cmd, commit_chain):
        head_sha = repo.refs.read_head()
        tree_id = repo.database.load(head_sha).tree
        spec = f"{tree_id}^^"

        _, _, _, stderr = legit_cmd("branch", "topic", spec)
        expected = (
            f"error: object {tree_id} is a tree, not a commit\n"
            f"fatal: Not a valid object name: '{spec}'.\n"
        )
        assert stderr.getvalue() == expected

    def test_lists_existing_branches(self, repo, legit_cmd, commit_chain):
        legit_cmd("branch", "new-feature")
        _, _, stdout, _ = legit_cmd("branch")
        assert stdout.getvalue() == "* master\n  new-feature\n"

    def test_lists_existing_branches_with_verbose_info(self, repo, legit_cmd, commit_chain):
        # master → third; new-feature → second
        head_sha = repo.refs.read_head()
        b_oid = head_sha
        b_commit = repo.database.load(b_oid)
        b_short = repo.database.short_oid(b_oid)
        b_msg = b_commit.message.strip()

        legit_cmd("branch", "new-feature", "HEAD^")
        a_oid = repo.refs.read_ref("new-feature")
        a_commit = repo.database.load(a_oid)
        a_short = repo.database.short_oid(a_oid)
        a_msg = a_commit.message.strip()

        _, _, stdout, _ = legit_cmd("branch", "--verbose")
        expected = (
            f"* master{' ' * (len('new-feature') - len('master') + 1)}{b_short} {b_msg}\n"
            f"  new-feature {a_short} {a_msg}\n"
        )
        assert stdout.getvalue() == expected

    def test_deletes_a_branch(self, repo, legit_cmd, commit_chain):
        head_sha = repo.refs.read_head()
        legit_cmd("branch", "bug-fix")

        cmd, _, stdout, _ = legit_cmd("branch", "-D", "bug-fix")
        assert stdout.getvalue() == f"Deleted branch 'bug-fix' (was {repo.database.short_oid(head_sha)}).\n"

        names = [r.short_name for r in repo.refs.list_branches()]
        assert "bug-fix" not in names

    def test_fails_to_delete_nonexistent_branch(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("branch", "-D", "no-such-branch")
        assert cmd.status == 1
        assert stderr.getvalue() == "error: branch 'no-such-branch' not found.\n"

