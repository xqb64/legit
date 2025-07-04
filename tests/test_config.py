import pytest
from tests.conftest import assert_status, assert_stdout, assert_stderr

class TestConfig:
    def test_returns_1_for_unknown_variables(self, legit_cmd):
        cmd, _, _, _ = legit_cmd("config", "--local", "no.such")
        assert_status(cmd, 1)

    def test_returns_1_when_key_is_invalid(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("config", "--local", "0.0")
        assert_status(cmd, 1)
        assert_stderr(stderr, "error: invalid key: 0.0\n")

    def test_returns_2_when_no_section_is_given(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("config", "--local", "no")
        assert_status(cmd, 2)
        assert_stderr(stderr, "error: key does not contain a section: no\n")

    def test_returns_the_value_of_a_set_variable(self, legit_cmd):
        legit_cmd("config", "core.editor", "ed")

        cmd, _, stdout, _ = legit_cmd("config", "--local", "Core.Editor")
        assert_status(cmd, 0)
        assert_stdout(stdout, "ed\n")

    def test_returns_the_value_of_a_set_variable_in_subsection(self, legit_cmd):
        legit_cmd("config", "remote.origin.url", "git@github.com:jcoglan.jit")

        cmd, _, stdout, _ = legit_cmd("config", "--local", "Remote.origin.URL")
        assert_status(cmd, 0)
        assert_stdout(stdout, "git@github.com:jcoglan.jit\n")

    def test_unsets_a_variable(self, legit_cmd):
        legit_cmd("config", "core.editor", "ed")
        legit_cmd("config", "--unset", "core.editor")

        cmd, _, _, _ = legit_cmd("config", "--local", "Core.Editor")
        assert_status(cmd, 1)

    class TestMultiValuedVariables:
        @pytest.fixture(autouse=True)
        def setup(self, legit_cmd):
            legit_cmd("config", "--add", "remote.origin.fetch", "master")
            legit_cmd("config", "--add", "remote.origin.fetch", "topic")

        def test_returns_the_last_value(self, legit_cmd):
            cmd, _, stdout, _ = legit_cmd("config", "remote.origin.fetch")
            assert_status(cmd, 0)
            assert_stdout(stdout, "topic\n")

        def test_returns_all_the_values(self, legit_cmd):
            cmd, _, stdout, _ = legit_cmd("config", "--get-all", "remote.origin.fetch")
            assert_status(cmd, 0)
            assert_stdout(stdout, "master\ntopic\n")

        def test_returns_5_on_trying_to_set_a_variable(self, legit_cmd):
            cmd, _, _, _ = legit_cmd("config", "remote.origin.fetch", "new-value")
            assert_status(cmd, 5)

            cmd2, _, stdout, _ = legit_cmd("config", "--get-all", "remote.origin.fetch")
            assert_status(cmd2, 0)
            assert_stdout(stdout, "master\ntopic\n")

        def test_replaces_a_variable(self, legit_cmd):
            legit_cmd("config", "--replace-all", "remote.origin.fetch", "new-value")

            cmd, _, stdout, _ = legit_cmd("config", "--get-all", "remote.origin.fetch")
            assert_status(cmd, 0)
            assert_stdout(stdout, "new-value\n")

        def test_returns_5_on_trying_to_unset_a_variable(self, legit_cmd):
            cmd, _, _, _ = legit_cmd("config", "--unset", "remote.origin.fetch")
            assert_status(cmd, 5)

            cmd2, _, stdout, _ = legit_cmd("config", "--get-all", "remote.origin.fetch")
            assert_status(cmd2, 0)
            assert_stdout(stdout, "master\ntopic\n")

        def test_unsets_all_values_for_a_variable(self, legit_cmd):
            legit_cmd("config", "--unset-all", "remote.origin.fetch")

            cmd, _, _, _ = legit_cmd("config", "--get-all", "remote.origin.fetch")
            assert_status(cmd, 1)

    def test_removes_a_section(self, legit_cmd):
        legit_cmd("config", "core.editor", "ed")
        legit_cmd("config", "remote.origin.url", "ssh://example.com/repo")
        legit_cmd("config", "--remove-section", "core")

        cmd1, _, stdout1, _ = legit_cmd("config", "--local", "remote.origin.url")
        assert_status(cmd1, 0)
        assert_stdout(stdout1, "ssh://example.com/repo\n")

        cmd2, _, _, _ = legit_cmd("config", "--local", "core.editor")
        assert_status(cmd2, 1)

    def test_removes_a_subsection(self, legit_cmd):
        legit_cmd("config", "core.editor", "ed")
        legit_cmd("config", "remote.origin.url", "ssh://example.com/repo")
        legit_cmd("config", "--remove-section", "remote.origin")

        cmd1, _, stdout1, _ = legit_cmd("config", "--local", "core.editor")
        assert_status(cmd1, 0)
        assert_stdout(stdout1, "ed\n")

        cmd2, _, _, _ = legit_cmd("config", "--local", "remote.origin.url")
        assert_status(cmd2, 1)
