import pytest
from legit.editor import Editor
from legit.rev_list import RevList

@pytest.fixture
def stub_editor(monkeypatch):
   stub_msg = "third [amended]"
   def fake_edit(path, command=None, *, block):
       if block:
           block(Editor(path, command))
       return stub_msg
   monkeypatch.setattr(Editor, 'edit', fake_edit)
   return stub_msg

@pytest.fixture
def commit_change(write_file, legit_cmd, commit):
    def _commit_change(content):
        write_file("file.txt", content)
        legit_cmd("add", ".")
        commit(content)
    return _commit_change


class TestCommittingToBranches:
    @pytest.fixture(autouse=True)
    def setup_repo(self, write_file, legit_cmd, commit):
        for msg in ["first", "second", "third"]:
            write_file("file.txt", msg)
            legit_cmd("add", ".")
            commit(msg)
        legit_cmd("branch", "topic")
        legit_cmd("checkout", "topic")

    def test_advances_branch_pointer(self, repo, resolve_revision, commit_change):
        head_before = repo.refs.read_ref("HEAD")

        commit_change("change")

        head_after = repo.refs.read_ref("HEAD")
        branch_after = repo.refs.read_ref("topic")

        assert head_before != head_after
        assert head_after == branch_after
        assert head_before == resolve_revision("@^")

    def test_advances_HEAD_on_detached(self, repo, legit_cmd, commit_change):
        # Detached HEAD scenario
        legit_cmd("checkout", "@")
        head_before = repo.refs.read_ref("HEAD")

        commit_change("change")
        head_after = repo.refs.read_ref("HEAD")

        assert head_before != head_after

    def test_does_not_advance_detached_branch(self, legit_cmd, repo, commit_change):
        legit_cmd("checkout", "@")
        branch_before = repo.refs.read_ref("topic")

        commit_change("change")
        branch_after = repo.refs.read_ref("topic")

        assert branch_before == branch_after

    def test_leaves_HEAD_ahead_of_branch(self, repo, legit_cmd, commit_change, resolve_revision):
        legit_cmd("checkout", "@")
        commit_change("change")

        assert repo.refs.read_ref("topic") == resolve_revision("@^")

    def test_concurrent_branches_advance_from_shared_parent(self, legit_cmd, commit_change, resolve_revision):
        legit_cmd("branch", "fork", "@^")
        commit_change("A")
        commit_change("B")
        legit_cmd("checkout", "fork")
        commit_change("C")

        assert resolve_revision("topic") != resolve_revision("fork")
        assert resolve_revision("topic~3") == resolve_revision("fork^")

class TestReusingMessages:
    @pytest.fixture(autouse=True)
    def setup_one_commit(self, write_file, legit_cmd, commit):
        write_file("file.txt", "1")
        legit_cmd("add", ".")
        commit("first")

    def test_reuses_message_from_previous_commit(self, write_file, legit_cmd, repo):
        write_file("file.txt", "2")
        legit_cmd("add", ".")
        legit_cmd("commit", "-C", "@")

        revs = RevList(repo, ["HEAD"])
        messages = [c.message.strip() for c in revs.each()]
        assert messages == ["first", "first"]

class TestAmendingCommits:
    @pytest.fixture(autouse=True)
    def setup_three_commits(self, write_file, legit_cmd, commit):
        for msg in ["first", "second", "third"]:
            write_file("file.txt", msg)
            legit_cmd("add", ".")
            commit(msg)

    def test_replaces_last_commit_message(self, repo, stub_editor, legit_cmd):
        legit_cmd("commit", "--amend")
        revs = RevList(repo, ["HEAD"])
        messages = [c.message.strip() for c in revs.each()]
        assert messages == ["third [amended]", "second", "first"]

    def test_replaces_last_commit_tree(self, write_file, legit_cmd, load_commit, repo):
        write_file("another.txt", "1")
        legit_cmd("add", "another.txt")
        legit_cmd("commit", "--amend")

        commit_obj = load_commit("HEAD")
        diff = repo.database.tree_diff(commit_obj.parent, commit_obj.oid)
        paths = sorted(str(p) for p in diff.keys())
        assert paths == ["another.txt", "file.txt"]

class TestConfiguringAnAuthor:
    @pytest.fixture(autouse=True)
    def setup(self, legit_cmd):
        legit_cmd("config", "user.name", "A. N. User")
        legit_cmd("config", "user.email", "user@example.com")

    def test_it_uses_the_author_information_from_the_config(self, write_file, legit_cmd, commit, load_commit):
        write_file("file.txt", "1")
        legit_cmd("add", ".")
        commit("first", None, False)

        head = load_commit("@")

        assert "A. N. User" == head.author.name
        assert "user@example.com" == head.author.email



