import textwrap
from datetime import datetime, timedelta
import pytest
from tests.conftest import assert_stdout


@pytest.fixture
def commit_file(write_file, legit_cmd, commit):
    """Fixture to commit a single file."""
    def _commit_file(msg, time=None):
        write_file("file.txt", msg)
        legit_cmd("add", ".")
        commit(msg, time)
    return _commit_file


@pytest.fixture
def commit_tree(write_file, legit_cmd, commit):
    """Fixture to commit a tree of files."""
    def _commit_tree(msg, files, time=None):
        for path, contents in files.items():
            write_file(path, contents)
        legit_cmd("add", ".")
        commit(msg, time)
    return _commit_tree


# Fixtures for the first set of tests (formerly TestWithAChainOfCommits)

@pytest.fixture
def chain_of_commits(commit_file, legit_cmd, load_commit):
    """Fixture to create a chain of three commits (A, B, C) and a 'topic' branch."""
    msgs = ["A", "B", "C"]
    for msg in msgs:
        commit_file(msg)
    legit_cmd("branch", "topic", "@^^")
    commits = [load_commit(rev) for rev in ["@", "@^", "@^^"]]
    return commits


# Tests formerly in TestWithAChainOfCommits

@pytest.mark.usefixtures("chain_of_commits")
def test_prints_a_log_in_medium_format(legit_cmd, chain_of_commits):
    """
    Verifies that 'legit log' without arguments prints the commit history in the medium format.
    """
    commits = chain_of_commits
    cmd, stdin, stdout, stderr = legit_cmd("log")
    expected_log = textwrap.dedent(f"""\
        commit {commits[0].oid}
        Author: A. U. Thor <author@example.com>
        Date:   {commits[0].author.readable_time()}

            C

        commit {commits[1].oid}
        Author: A. U. Thor <author@example.com>
        Date:   {commits[1].author.readable_time()}

            B

        commit {commits[2].oid}
        Author: A. U. Thor <author@example.com>
        Date:   {commits[2].author.readable_time()}

            A
        """)
    assert_stdout(stdout, expected_log)


@pytest.mark.usefixtures("chain_of_commits")
def test_medium_format_with_abbrev_ids(legit_cmd, chain_of_commits, repo):
    """
    Verifies that 'legit log --abbrev-commit' prints the log with abbreviated commit IDs.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--abbrev-commit")
    expected = textwrap.dedent(f"""\
        commit {repo.database.short_oid(commits[0].oid)}
        Author: A. U. Thor <author@example.com>
        Date:   {commits[0].author.readable_time()}

            C

        commit {repo.database.short_oid(commits[1].oid)}
        Author: A. U. Thor <author@example.com>
        Date:   {commits[1].author.readable_time()}

            B

        commit {repo.database.short_oid(commits[2].oid)}
        Author: A. U. Thor <author@example.com>
        Date:   {commits[2].author.readable_time()}

            A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_oneline_format(legit_cmd, chain_of_commits, repo):
    """
    Verifies that 'legit log --oneline' prints the log in a compact, one-line format.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(commits[0].oid)} C
        {repo.database.short_oid(commits[1].oid)} B
        {repo.database.short_oid(commits[2].oid)} A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_oneline_without_abbrev(legit_cmd, chain_of_commits):
    """
    Verifies that 'legit log --pretty=oneline' without abbreviation shows full commit IDs.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--pretty=oneline")
    expected = textwrap.dedent(f"""\
        {commits[0].oid} C
        {commits[1].oid} B
        {commits[2].oid} A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_oneline_from_specified_commit(legit_cmd, chain_of_commits):
    """
    Verifies that 'legit log' can start from a specified commit.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--pretty=oneline", "@^")
    expected = textwrap.dedent(f"""\
        {commits[1].oid} B
        {commits[2].oid} A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_short_decorations(legit_cmd, chain_of_commits, repo):
    """
    Verifies that 'legit log --decorate=short' shows branch names next to commits.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "--decorate=short")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(commits[0].oid)} (HEAD -> master) C
        {repo.database.short_oid(commits[1].oid)} B
        {repo.database.short_oid(commits[2].oid)} (topic) A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_detached_head_decorations(legit_cmd, chain_of_commits, repo):
    """
    Verifies that decorations correctly indicate a detached HEAD state.
    """
    commits = chain_of_commits
    legit_cmd("checkout", "@")
    _, _, stdout, _ = legit_cmd("log", "--oneline", "--decorate=short")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(commits[0].oid)} (HEAD, master) C
        {repo.database.short_oid(commits[1].oid)} B
        {repo.database.short_oid(commits[2].oid)} (topic) A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_full_decorations(legit_cmd, chain_of_commits, repo):
    """
    Verifies that 'legit log --decorate=full' shows full ref paths.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "--decorate=full")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(commits[0].oid)} (HEAD -> refs/heads/master) C
        {repo.database.short_oid(commits[1].oid)} B
        {repo.database.short_oid(commits[2].oid)} (refs/heads/topic) A
        """)
    assert_stdout(stdout, expected)


@pytest.mark.usefixtures("chain_of_commits")
def test_oneline_with_patches(legit_cmd, chain_of_commits, repo):
    """
    Verifies that 'legit log --patch' includes diffs for each commit.
    """
    commits = chain_of_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "--patch")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(commits[0].oid)} C
        diff --git a/file.txt b/file.txt
        index 7371f47..96d80cd 100644
        --- a/file.txt
        +++ b/file.txt
        @@ -1,1 +1,1 @@
        -B
        +C
        {repo.database.short_oid(commits[1].oid)} B
        diff --git a/file.txt b/file.txt
        index 8c7e5a6..7371f47 100644
        --- a/file.txt
        +++ b/file.txt
        @@ -1,1 +1,1 @@
        -A
        +B
        {repo.database.short_oid(commits[2].oid)} A
        diff --git a/file.txt b/file.txt
        new file mode 100644
        index 0000000..8c7e5a6
        --- /dev/null
        +++ b/file.txt
        @@ -0,0 +1,1 @@
        +A
        """)
    assert_stdout(stdout, expected)


# Fixture for path filtering tests (formerly TestLogPathFiltering)

@pytest.fixture
def path_filtering_commits(commit_tree, load_commit):
    """Fixture to create a commit history for testing path filtering."""
    commit_tree("first", {
        "a/1.txt": "1",
        "b/c/2.txt": "2",
    })
    commit_tree("second", {
        "a/1.txt": "10",
        "b/3.txt": "3",
    })
    commit_tree("third", {
        "b/c/2.txt": "4",
    })
    return [load_commit(rev) for rev in ["@^^", "@^", "@"]]


# Tests for path filtering (formerly TestLogPathFiltering)

def test_logs_commits_that_change_a_file(legit_cmd, repo, path_filtering_commits):
    """Verifies that log can be filtered by a specific file path."""
    c1, c2, c3 = path_filtering_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "a/1.txt")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(c2.oid)} second
        {repo.database.short_oid(c1.oid)} first
        """)
    assert_stdout(stdout, expected)


def test_logs_commits_that_change_a_directory(legit_cmd, repo, path_filtering_commits):
    """Verifies that log can be filtered by a directory path."""
    c1, c2, c3 = path_filtering_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "b")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(c3.oid)} third
        {repo.database.short_oid(c2.oid)} second
        {repo.database.short_oid(c1.oid)} first
        """)
    assert_stdout(stdout, expected)


def test_logs_commits_that_change_dir_and_one_of_its_files(legit_cmd, repo, path_filtering_commits):
    """Verifies that filtering by a directory and a file within it works as expected."""
    c1, c2, c3 = path_filtering_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "b", "b/3.txt")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(c3.oid)} third
        {repo.database.short_oid(c2.oid)} second
        {repo.database.short_oid(c1.oid)} first
        """)
    assert_stdout(stdout, expected)


def test_logs_commits_that_change_a_nested_directory(legit_cmd, repo, path_filtering_commits):
    """Verifies that filtering by a nested directory path works correctly."""
    c1, c2, c3 = path_filtering_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "b/c")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(c3.oid)} third
        {repo.database.short_oid(c1.oid)} first
        """)
    assert_stdout(stdout, expected)


def test_logs_with_patches_for_selected_files(legit_cmd, repo, path_filtering_commits):
    """Verifies that patches shown by log are correctly filtered by file path."""
    c1, c2, c3 = path_filtering_commits
    _, _, stdout, _ = legit_cmd("log", "--oneline", "--patch", "a/1.txt")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(c2.oid)} second
        diff --git a/a/1.txt b/a/1.txt
        index 56a6051..9a03714 100644
        --- a/a/1.txt
        +++ b/a/1.txt
        @@ -1,1 +1,1 @@
        -1
        +10
        {repo.database.short_oid(c1.oid)} first
        diff --git a/a/1.txt b/a/1.txt
        new file mode 100644
        index 0000000..56a6051
        --- /dev/null
        +++ b/a/1.txt
        @@ -0,0 +1,1 @@
        +1
        """)
    assert_stdout(stdout, expected)


# Fixture for branch history tests (formerly TestLogBranchHistory)

@pytest.fixture
def branch_history_setup(commit_file, legit_cmd, resolve_revision):
    """Fixture to create a history with master and topic branches."""
    for n in range(1, 4):
        commit_file(f"master-{n}")
    
    legit_cmd("branch", "topic", "master^")
    legit_cmd("checkout", "topic")
    
    branch_time = datetime.now() + timedelta(seconds=10)
    for n in range(1, 5):
        commit_file(f"topic-{n}", branch_time)
        
    master_oids = [resolve_revision(f"master~{n}") for n in range(0, 3)]
    topic_oids = [resolve_revision(f"topic~{n}") for n in range(0, 4)]
    
    return {
        "master": master_oids,
        "topic": topic_oids,
        "branch_time": branch_time,
    }


# Tests for branch history (formerly TestLogBranchHistory)

def test_combined_history_of_multiple_branches(legit_cmd, repo, branch_history_setup):
    """Verifies that the log can show the combined history of multiple branches."""
    m, t = branch_history_setup["master"], branch_history_setup["topic"]
    _, _, stdout, _ = legit_cmd(
        "log", "--oneline", "--decorate=short", "master", "topic"
    )
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[0])} (HEAD -> topic) topic-4
        {repo.database.short_oid(t[1])} topic-3
        {repo.database.short_oid(t[2])} topic-2
        {repo.database.short_oid(t[3])} topic-1
        {repo.database.short_oid(m[0])} (master) master-3
        {repo.database.short_oid(m[1])} master-2
        {repo.database.short_oid(m[2])} master-1
        """)
    assert_stdout(stdout, expected)


def test_diff_from_one_branch_to_another(legit_cmd, repo, branch_history_setup):
    """Verifies log's ability to show commits reachable from one branch but not another."""
    m, t = branch_history_setup["master"], branch_history_setup["topic"]
    # master..topic
    _, _, stdout, _ = legit_cmd("log", "--oneline", "master..topic")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[0])} topic-4
        {repo.database.short_oid(t[1])} topic-3
        {repo.database.short_oid(t[2])} topic-2
        {repo.database.short_oid(t[3])} topic-1
        """)
    assert_stdout(stdout, expected)

    # master ^topic (only master commits not in topic)
    m0 = m[0]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "master", "^topic")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(m0)} master-3
        """)
    assert_stdout(stdout, expected)


def test_excludes_long_branch_when_times_equal(legit_cmd, commit_file, repo, branch_history_setup):
    """
    Verifies that when commit times are equal, the log excludes commits from a longer
    side branch when using revision range.
    """
    branch_time = branch_history_setup["branch_time"]
    legit_cmd("branch", "side", "topic^^")
    legit_cmd("checkout", "side")
    for n in range(1, 11):
        commit_file(f"side-{n}", branch_time)
    
    _, _, stdout, _ = legit_cmd(
        "log", "--oneline", "side..topic", "^master"
    )
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(branch_history_setup['topic'][0])} topic-4
        {repo.database.short_oid(branch_history_setup['topic'][1])} topic-3
        """)
    assert_stdout(stdout, expected)


def test_logs_last_few_commits_on_branch(legit_cmd, repo, branch_history_setup):
    """Verifies that log can show a range of recent commits (e.g., @~3..)."""
    t = branch_history_setup["topic"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "@~3..")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[0])} topic-4
        {repo.database.short_oid(t[1])} topic-3
        {repo.database.short_oid(t[2])} topic-2
        """)
    assert_stdout(stdout, expected)


@pytest.fixture
def graph_of_commits_setup(commit_tree, legit_cmd, resolve_revision):
    """Fixture to create a complex commit graph with merges."""
    time = datetime.now()

    commit_tree("A", {"f.txt": "0", "g.txt": "0"}, time)
    commit_tree("B", {"f.txt": "B", "h.txt": "one\ntwo\nthree\n"}, time)

    for n in ["C", "D"]:
        commit_tree(n, {"f.txt": n, "h.txt": f"{n}\ntwo\nthree\n"}, time + timedelta(seconds=1))

    legit_cmd("branch", "topic", "master~2")
    legit_cmd("checkout", "topic")

    for n in ["E", "F", "G", "H"]:
        commit_tree(n, {"g.txt": n, "h.txt": f"one\ntwo\n{n}\n"}, time + timedelta(seconds=2))

    legit_cmd("checkout", "master")
    legit_cmd("merge", "topic^", "-m", "J")

    commit_tree("K", {"f.txt": "K"}, time + timedelta(seconds=3))

    master_oids = [resolve_revision(f"master~{n}") for n in range(6)]
    topic_oids = [resolve_revision(f"topic~{n}") for n in range(4)]

    return {"master": master_oids, "topic": topic_oids}


# Tests for graph of commits (formerly TestLogWithGraphOfCommits)

def test_logs_concurrent_branches_leading_to_a_merge(legit_cmd, repo, graph_of_commits_setup):
    """Verifies that the log correctly displays a non-linear history with a merge."""
    m = graph_of_commits_setup["master"]
    t = graph_of_commits_setup["topic"]
    _, _, stdout, _ = legit_cmd("log", "--oneline")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(m[0])} K
        {repo.database.short_oid(m[1])} J
        {repo.database.short_oid(t[1])} G
        {repo.database.short_oid(t[2])} F
        {repo.database.short_oid(t[3])} E
        {repo.database.short_oid(m[2])} D
        {repo.database.short_oid(m[3])} C
        {repo.database.short_oid(m[4])} B
        {repo.database.short_oid(m[5])} A
        """)
    assert_stdout(stdout, expected)


def test_logs_the_first_parent_of_a_merge(legit_cmd, repo, graph_of_commits_setup):
    """Verifies that log can follow the first parent of a merge commit."""
    m = graph_of_commits_setup["master"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "master^^")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(m[2])} D
        {repo.database.short_oid(m[3])} C
        {repo.database.short_oid(m[4])} B
        {repo.database.short_oid(m[5])} A
        """)
    assert_stdout(stdout, expected)


def test_logs_the_second_parent_of_a_merge(legit_cmd, repo, graph_of_commits_setup):
    """Verifies that log can follow the second parent of a merge commit."""
    m = graph_of_commits_setup["master"]
    t = graph_of_commits_setup["topic"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "master^^2")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[1])} G
        {repo.database.short_oid(t[2])} F
        {repo.database.short_oid(t[3])} E
        {repo.database.short_oid(m[4])} B
        {repo.database.short_oid(m[5])} A
        """)
    assert_stdout(stdout, expected)


def test_logs_unmerged_commits_on_a_branch(legit_cmd, repo, graph_of_commits_setup):
    """Verifies that log can show commits on a topic branch that are not yet merged."""
    t = graph_of_commits_setup["topic"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "master..topic")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[0])} H
        """)
    assert_stdout(stdout, expected)


def test_does_not_show_patches_for_merge_commits(legit_cmd, repo, graph_of_commits_setup):
    """Verifies that by default, 'log --patch' does not show a patch for merge commits."""
    m = graph_of_commits_setup["master"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "--patch", "topic..master", "^master^^^")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(m[0])} K
        diff --git a/f.txt b/f.txt
        index 02358d2..449e49e 100644
        --- a/f.txt
        +++ b/f.txt
        @@ -1,1 +1,1 @@
        -D
        +K
        {repo.database.short_oid(m[1])} J
        {repo.database.short_oid(m[2])} D
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


def test_shows_combined_patches_for_merges(legit_cmd, repo, graph_of_commits_setup):
    """Verifies that 'log --cc' shows a combined diff for merge commits."""
    m = graph_of_commits_setup["master"]
    _, _, stdout, _ = legit_cmd("log", "--pretty=oneline", "--cc", "topic..master", "^master^^^")
    expected = textwrap.dedent(f"""\
        {m[0]} K
        diff --git a/f.txt b/f.txt
        index 02358d2..449e49e 100644
        --- a/f.txt
        +++ b/f.txt
        @@ -1,1 +1,1 @@
        -D
        +K
        {m[1]} J
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
        {m[2]} D
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


def test_does_not_list_merges_with_treesame_parents_for_prune_paths(legit_cmd, repo, graph_of_commits_setup):
    """
    Verifies that merges where a parent is tree-same are not listed when pruning paths.
    """
    m = graph_of_commits_setup["master"]
    t = graph_of_commits_setup["topic"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "g.txt")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[1])} G
        {repo.database.short_oid(t[2])} F
        {repo.database.short_oid(t[3])} E
        {repo.database.short_oid(m[5])} A
        """)
    assert_stdout(stdout, expected)

# Fixture for undone changes test (formerly part of TestWithUndoneChanges)

@pytest.fixture
def setup_undone_changes(commit_tree, legit_cmd, graph_of_commits_setup):
    """
    Fixture that builds upon the graph of commits by adding a branch
    where a change is made and then undone.
    """
    time = datetime.now()
    legit_cmd("branch", "aba", "master~4")
    legit_cmd("checkout", "aba")

    commit_tree("C", {"g.txt": "C"}, time + timedelta(seconds=1))
    commit_tree("0", {"g.txt": "0"}, time + timedelta(seconds=1))

    legit_cmd("merge", "topic^", "-m", "J")
    commit_tree("K", {"f.txt": "K"}, time + timedelta(seconds=3))
    
    return graph_of_commits_setup

def test_does_not_list_commits_on_the_filtered_branch_after_changes_undone(legit_cmd, repo, setup_undone_changes):
    """
    Verifies that the log correctly filters out a branch where a file was changed
    and then changed back to its original state.
    """
    m = setup_undone_changes["master"]
    t = setup_undone_changes["topic"]
    _, _, stdout, _ = legit_cmd("log", "--oneline", "g.txt")
    expected = textwrap.dedent(f"""\
        {repo.database.short_oid(t[1])} G
        {repo.database.short_oid(t[2])} F
        {repo.database.short_oid(t[3])} E
        {repo.database.short_oid(m[5])} A
        """)
    assert_stdout(stdout, expected)
