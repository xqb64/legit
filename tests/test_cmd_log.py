import textwrap
from datetime import datetime, timedelta
from enum import auto
from typing import Protocol, cast

import pytest

from legit.author import Author
from legit.commit import Commit as CommitObj
from legit.repository import Repository
from tests.cmd_helpers import assert_stdout
from tests.conftest import (
    Commit,
    LegitCmd,
    LoadCommit,
    ResolveRevision,
    WriteFile,
)


class CommitFile(Protocol):
    def __call__(self, msg: str, time: datetime | None = None) -> None: ...


class CommitTree(Protocol):
    def __call__(
        self, msg: str, files: dict[str, str], time: datetime | None = None
    ) -> None: ...


@pytest.fixture
def commit_file(
    write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit
) -> CommitFile:
    def _commit_file(msg: str, time: datetime | None = None) -> None:
        write_file("file.txt", msg)
        _ = legit_cmd("add", ".")
        commit(msg, time)

    return _commit_file


@pytest.fixture
def commit_tree(
    write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit
) -> CommitTree:
    def _commit_tree(
        msg: str, files: dict[str, str], time: datetime | None = None
    ) -> None:
        for path, contents in files.items():
            write_file(path, contents)
        _ = legit_cmd("add", ".")
        commit(msg, time)

    return _commit_tree


class TestWithAChainOfCommits:
    #   o---o---o
    #   A   B   C

    @pytest.fixture(autouse=True)
    def setup(
        self, commit_file: CommitFile, legit_cmd: LegitCmd, load_commit: LoadCommit
    ) -> None:
        msgs = ["A", "B", "C"]
        for msg in msgs:
            commit_file(msg)

        _ = legit_cmd("branch", "topic", "@^^")

        self.commits = [cast(CommitObj, load_commit(rev)) for rev in ["@", "@^", "@^^"]]

    def test_it_prints_a_log_in_medium_format(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log")
        expected_log = textwrap.dedent(f"""\
            commit {self.commits[0].oid}
            Author: A. U. Thor <author@example.com>
            Date:   {cast(Author, self.commits[0].author).readable_time()}
    
                C
    
            commit {self.commits[1].oid}
            Author: A. U. Thor <author@example.com>
            Date:   {cast(Author, self.commits[1].author).readable_time()}
    
                B
    
            commit {self.commits[2].oid}
            Author: A. U. Thor <author@example.com>
            Date:   {cast(Author, self.commits[2].author).readable_time()}
    
                A
            """)
        assert_stdout(stdout, expected_log)

    def test_it_prints_a_log_in_medium_format_with_abbreviated_commit_ids(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--abbrev-commit")
        expected = textwrap.dedent(f"""\
            commit {repo.database.short_oid(self.commits[0].oid)}
            Author: A. U. Thor <author@example.com>
            Date:   {cast(Author, self.commits[0].author).readable_time()}
    
                C
    
            commit {repo.database.short_oid(self.commits[1].oid)}
            Author: A. U. Thor <author@example.com>
            Date:   {cast(Author, self.commits[1].author).readable_time()}
    
                B
    
            commit {repo.database.short_oid(self.commits[2].oid)}
            Author: A. U. Thor <author@example.com>
            Date:   {cast(Author, self.commits[2].author).readable_time()}
    
                A
            """)
        assert_stdout(stdout, expected)

    def test_it_prints_a_log_in_oneline_format(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--oneline")
        expected = textwrap.dedent(f"""\
            {repo.database.short_oid(self.commits[0].oid)} C
            {repo.database.short_oid(self.commits[1].oid)} B
            {repo.database.short_oid(self.commits[2].oid)} A
            """)
        assert_stdout(stdout, expected)

    def test_it_print_a_log_in_oneline_format_without_abbreviated_commit_ids(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline")
        expected = textwrap.dedent(f"""\
            {self.commits[0].oid} C
            {self.commits[1].oid} B
            {self.commits[2].oid} A
            """)
        assert_stdout(stdout, expected)

    def test_it_prints_a_log_starting_from_a_specified_commit(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "@^")
        expected = textwrap.dedent(f"""\
            {self.commits[1].oid} B
            {self.commits[2].oid} A
            """)
        assert_stdout(stdout, expected)

    def test_it_prints_a_log_with_short_decorations(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "--decorate=short")
        expected = textwrap.dedent(f"""\
            {self.commits[0].oid} (HEAD -> master) C
            {self.commits[1].oid} B
            {self.commits[2].oid} (topic) A
            """)
        assert_stdout(stdout, expected)

    def test_it_prints_a_log_with_detached_heads(self, legit_cmd: LegitCmd) -> None:
        _ = legit_cmd("checkout", "@")
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "--decorate=short")
        expected = textwrap.dedent(f"""\
            {self.commits[0].oid} (HEAD, master) C
            {self.commits[1].oid} B
            {self.commits[2].oid} (topic) A
            """)
        assert_stdout(stdout, expected)

    def test_it_print_a_log_with_full_decorations(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "--decorate=full")
        expected = textwrap.dedent(f"""\
            {self.commits[0].oid} (HEAD -> refs/heads/master) C
            {self.commits[1].oid} B
            {self.commits[2].oid} (refs/heads/topic) A
            """)
        assert_stdout(stdout, expected)

    def test_it_print_a_log_with_patches(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "--patch")
        expected = textwrap.dedent(f"""\
            {self.commits[0].oid} C
            diff --git a/file.txt b/file.txt
            index 7371f47..96d80cd 100644
            --- a/file.txt
            +++ b/file.txt
            @@ -1,1 +1,1 @@
            -B
            +C
            {self.commits[1].oid} B
            diff --git a/file.txt b/file.txt
            index 8c7e5a6..7371f47 100644
            --- a/file.txt
            +++ b/file.txt
            @@ -1,1 +1,1 @@
            -A
            +B
            {self.commits[2].oid} A
            diff --git a/file.txt b/file.txt
            new file mode 100644
            index 0000000..8c7e5a6
            --- /dev/null
            +++ b/file.txt
            @@ -0,0 +1,1 @@
            +A
            """)
        assert_stdout(stdout, expected)


class TestWithCommitsChangingDifferentFiles:
    @pytest.fixture(autouse=True)
    def setup(self, commit_tree: CommitTree, load_commit: LoadCommit) -> None:
        commit_tree(
            "first",
            {
                "a/1.txt": "1",
                "b/c/2.txt": "2",
            },
        )
        commit_tree(
            "second",
            {
                "a/1.txt": "10",
                "b/3.txt": "3",
            },
        )
        commit_tree(
            "third",
            {
                "b/c/2.txt": "4",
            },
        )
        self.commits = [load_commit(rev) for rev in ["@^^", "@^", "@"]]

    def test_it_logs_commits_that_change_a_file(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "a/1.txt")
        expected = textwrap.dedent(f"""\
            {self.commits[1].oid} second
            {self.commits[0].oid} first
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_commits_that_change_a_directory(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "b")
        expected = textwrap.dedent(f"""\
            {self.commits[2].oid} third
            {self.commits[1].oid} second
            {self.commits[0].oid} first
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_commits_that_change_a_directory_and_one_of_its_files(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "b", "b/3.txt")
        expected = textwrap.dedent(f"""\
            {self.commits[2].oid} third
            {self.commits[1].oid} second
            {self.commits[0].oid} first
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_commits_that_change_a_nested_directory(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "b/c")
        expected = textwrap.dedent(f"""\
            {self.commits[2].oid} third
            {self.commits[0].oid} first
            """)
        assert_stdout(stdout, expected)

    def test_logs_with_patches_for_selected_files(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "--patch", "a/1.txt")
        expected = textwrap.dedent(f"""\
            {self.commits[1].oid} second
            diff --git a/a/1.txt b/a/1.txt
            index 56a6051..9a03714 100644
            --- a/a/1.txt
            +++ b/a/1.txt
            @@ -1,1 +1,1 @@
            -1
            +10
            {self.commits[0].oid} first
            diff --git a/a/1.txt b/a/1.txt
            new file mode 100644
            index 0000000..56a6051
            --- /dev/null
            +++ b/a/1.txt
            @@ -0,0 +1,1 @@
            +1
            """)
        assert_stdout(stdout, expected)


class TestWithATreeOfCommits:
    #  m1  m2  m3
    #   o---o---o [master]
    #        \
    #         o---o---o---o [topic]
    #        t1  t2  t3  t4

    @pytest.fixture(autouse=True)
    def setup(
        self,
        commit_file: CommitFile,
        legit_cmd: LegitCmd,
        resolve_revision: ResolveRevision,
    ) -> None:
        for n in range(1, 4):
            commit_file(f"master-{n}")

        _ = legit_cmd("branch", "topic", "master^")
        _ = legit_cmd("checkout", "topic")

        self.branch_time = datetime.now().astimezone() + timedelta(seconds=10)
        for n in range(1, 5):
            commit_file(f"topic-{n}", self.branch_time)

        self.master = [resolve_revision(f"master~{n}") for n in range(0, 3)]
        self.topic = [resolve_revision(f"topic~{n}") for n in range(0, 4)]

    def test_it_logs_the_combined_history_of_multiple_branches(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd(
            "log", "--pretty=oneline", "--decorate=short", "master", "topic"
        )
        expected = textwrap.dedent(f"""\
            {self.topic[0]} (HEAD -> topic) topic-4
            {self.topic[1]} topic-3
            {self.topic[2]} topic-2
            {self.topic[3]} topic-1
            {self.master[0]} (master) master-3
            {self.master[1]} master-2
            {self.master[2]} master-1
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_the_difference__from_one_branch_to_another(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "master..topic")
        expected = textwrap.dedent(f"""\
            {self.topic[0]} topic-4
            {self.topic[1]} topic-3
            {self.topic[2]} topic-2
            {self.topic[3]} topic-1
            """)
        assert_stdout(stdout, expected)

        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "master", "^topic")
        expected = textwrap.dedent(f"""\
            {self.master[0]} master-3
            """)
        assert_stdout(stdout, expected)

    def test_it_excludes_long_branch_when_commit_times_equal(
        self,
        legit_cmd: LegitCmd,
        commit_file: CommitFile,
    ) -> None:
        _ = legit_cmd("branch", "side", "topic^^")
        _ = legit_cmd("checkout", "side")
        for n in range(1, 11):
            commit_file(f"side-{n}", self.branch_time)

        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "side..topic", "^master")

        expected = textwrap.dedent(f"""\
            {self.topic[0]} topic-4
            {self.topic[1]} topic-3
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_the_last_few_commits_on_a_branch(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "@~3..")
        expected = textwrap.dedent(f"""\
            {self.topic[0]} topic-4
            {self.topic[1]} topic-3
            {self.topic[2]} topic-2
            """)
        assert_stdout(stdout, expected)


class TestWithAGraphOfCommits:
    #   A   B   C   D   J   K
    #   o---o---o---o---o---o [master]
    #        \         /
    #         o---o---o---o [topic]
    #         E   F   G   H

    @pytest.fixture(autouse=True)
    def setup(
        self,
        commit_tree: CommitTree,
        legit_cmd: LegitCmd,
        resolve_revision: ResolveRevision,
    ) -> None:
        time = datetime.now().astimezone()

        commit_tree("A", {"f.txt": "0", "g.txt": "0"}, time)
        commit_tree("B", {"f.txt": "B", "h.txt": "one\ntwo\nthree\n"}, time)

        for n in ["C", "D"]:
            commit_tree(
                n,
                {"f.txt": n, "h.txt": f"{n}\ntwo\nthree\n"},
                time + timedelta(seconds=1),
            )

        _ = legit_cmd("branch", "topic", "master~2")
        _ = legit_cmd("checkout", "topic")

        for n in ["E", "F", "G", "H"]:
            commit_tree(
                n,
                {"g.txt": n, "h.txt": f"one\ntwo\n{n}\n"},
                time + timedelta(seconds=2),
            )

        _ = legit_cmd("checkout", "master")
        _ = legit_cmd("merge", "topic^", "-m", "J")

        commit_tree("K", {"f.txt": "K"}, time + timedelta(seconds=3))

        self.master = [resolve_revision(f"master~{n}") for n in range(6)]
        self.topic = [resolve_revision(f"topic~{n}") for n in range(4)]

    def test_it_logs_concurrent_branches_leading_to_a_merge(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline")
        expected = textwrap.dedent(f"""\
            {self.master[0]} K
            {self.master[1]} J
            {self.topic[1]} G
            {self.topic[2]} F
            {self.topic[3]} E
            {self.master[2]} D
            {self.master[3]} C
            {self.master[4]} B
            {self.master[5]} A
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_the_first_parent_of_a_merge(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "master^^")
        expected = textwrap.dedent(f"""\
            {self.master[2]} D
            {self.master[3]} C
            {self.master[4]} B
            {self.master[5]} A
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_the_second_parent_of_a_merge(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "master^^2")
        expected = textwrap.dedent(f"""\
            {self.topic[1]} G
            {self.topic[2]} F
            {self.topic[3]} E
            {self.master[4]} B
            {self.master[5]} A
            """)
        assert_stdout(stdout, expected)

    def test_it_logs_unmerged_commits_on_a_branch(self, legit_cmd: LegitCmd) -> None:
        _, _, stdout, _ = legit_cmd("log", "--pretty=oneline", "master..topic")
        expected = textwrap.dedent(f"""\
            {self.topic[0]} H
            """)
        assert_stdout(stdout, expected)

    def test_it_does_not_show_patches_for_merge_commits(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd(
            "log", "--pretty=oneline", "--patch", "topic..master", "^master^^^"
        )
        expected = textwrap.dedent(f"""\
            {self.master[0]} K
            diff --git a/f.txt b/f.txt
            index 02358d2..449e49e 100644
            --- a/f.txt
            +++ b/f.txt
            @@ -1,1 +1,1 @@
            -D
            +K
            {self.master[1]} J
            {self.master[2]} D
            diff --git a/f.txt b/f.txt
            index 96d80cd..02358d2 100644
            --- a/f.txt
            +++ b/f.txt
            @@ -1,1 +1,1 @@
            -C
            +D
            diff --git a/h.txt b/h.txt
            index 4e5ce14..4139691 100644
            --- a/h.txt
            +++ b/h.txt
            @@ -1,3 +1,3 @@
            -C
            +D
             two
             three
            """)
        assert_stdout(stdout, expected)

    def test_it_shows_combined_patches_for_merges(self, legit_cmd: LegitCmd) -> None:
        *_, stdout, _ = legit_cmd(
            "log", "--pretty=oneline", "--cc", "topic..master", "^master^^^"
        )
        expected = textwrap.dedent(f"""\
            {self.master[0]} K
            diff --git a/f.txt b/f.txt
            index 02358d2..449e49e 100644
            --- a/f.txt
            +++ b/f.txt
            @@ -1,1 +1,1 @@
            -D
            +K
            {self.master[1]} J
            diff --cc h.txt
            index 4139691,f3e97ee..4e78f4f
            --- a/h.txt
            +++ b/h.txt
            @@@ -1,3 -1,3 +1,3 @@@
             -one
             +D
              two
            - three
            + G
            {self.master[2]} D
            diff --git a/f.txt b/f.txt
            index 96d80cd..02358d2 100644
            --- a/f.txt
            +++ b/f.txt
            @@ -1,1 +1,1 @@
            -C
            +D
            diff --git a/h.txt b/h.txt
            index 4e5ce14..4139691 100644
            --- a/h.txt
            +++ b/h.txt
            @@ -1,3 +1,3 @@
            -C
            +D
             two
             three
            """)
        assert_stdout(stdout, expected)

    def test_it_does_not_list_merges_with_treesame_parents_for_prune_paths(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "g.txt")
        expected = textwrap.dedent(f"""\
            {self.topic[1]} G
            {self.topic[2]} F
            {self.topic[3]} E
            {self.master[5]} A
            """)
        assert_stdout(stdout, expected)


class TestWithChangesThatAreUndoneOnABranchLeadingToAMerge:
    @pytest.fixture(autouse=True)
    def setup(
        self,
        commit_tree: CommitTree,
        legit_cmd: LegitCmd,
        resolve_revision: ResolveRevision,
    ) -> None:
        time = datetime.now().astimezone()

        commit_tree("A", {"f.txt": "0", "g.txt": "0"}, time)
        commit_tree("B", {"f.txt": "B", "h.txt": "one\ntwo\nthree\n"}, time)

        for n in ["C", "D"]:
            commit_tree(
                n,
                {"f.txt": n, "h.txt": f"{n}\ntwo\nthree\n"},
                time + timedelta(seconds=1),
            )

        _ = legit_cmd("branch", "topic", "master~2")
        _ = legit_cmd("checkout", "topic")

        for n in ["E", "F", "G", "H"]:
            commit_tree(
                n,
                {"g.txt": n, "h.txt": f"one\ntwo\n{n}\n"},
                time + timedelta(seconds=2),
            )

        _ = legit_cmd("checkout", "master")
        _ = legit_cmd("merge", "topic^", "-m", "J")

        commit_tree("K", {"f.txt": "K"}, time + timedelta(seconds=3))

        self.master = [resolve_revision(f"master~{n}") for n in range(6)]
        self.topic = [resolve_revision(f"topic~{n}") for n in range(4)]

        time = datetime.now().astimezone()

        _ = legit_cmd("branch", "aba", "master~4")
        _ = legit_cmd("checkout", "aba")

        commit_tree("C", {"g.txt": "C"}, time + timedelta(seconds=1))
        commit_tree("0", {"g.txt": "0"}, time + timedelta(seconds=1))

        _ = legit_cmd("merge", "topic^", "-m", "J")
        commit_tree("K", {"f.txt": "K"}, time + timedelta(seconds=3))

    def test_it_does_not_list_commits_on_the_filtered_branch(
        self, legit_cmd: LegitCmd
    ) -> None:
        *_, stdout, _ = legit_cmd("log", "--pretty=oneline", "g.txt")
        expected = textwrap.dedent(f"""\
            {self.topic[1]} G
            {self.topic[2]} F
            {self.topic[3]} E
            {self.master[5]} A
            """)
        assert_stdout(stdout, expected)
