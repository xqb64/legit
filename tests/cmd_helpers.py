def assert_status(cmd, expected):
    assert cmd.status == expected, f"Expected status {expected}, got {cmd.status}"


def assert_stdout(stdout, expected):
    stdout.seek(0)
    data = stdout.read()
    assert data == expected, f"Expected stdout {expected!r}, got {data!r}"


def assert_stderr(stderr, expected):
    stderr.seek(0)
    data = stderr.read()
    assert data == expected, f"Expected stderr {expected!r}, got {data!r}"


