from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import click

from legit.cmd_base import Base
from legit.command import Command

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 120,
}


def run_cmd(cmd_name: str, *args: str) -> None:
    argv: list[str] = ["legit", cmd_name, *args]

    cmd: Base = Command.execute(
        Path.cwd(),
        os.environ.copy(),
        argv,
        sys.stdin,
        sys.stdout,
        sys.stderr,
    )

    sys.exit(cmd.status)


@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument(
    "path", type=click.Path(file_okay=False, path_type=Path), required=False
)
def init(path: Path | None) -> None:
    """Create an empty legit repository or reinitialize an existing one."""
    run_cmd("init", *(str(path),) if path is not None else ())


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
def add(paths: tuple[Path, ...]) -> None:
    """Add file contents to the index."""
    if not paths:
        click.echo("error: pathspec required", err=True)
        raise SystemExit(1)

    run_cmd("add", *(str(p) for p in paths))


@cli.command()
@click.option(
    "-m",
    "--message",
    "message",
    type=str,
    help="Use the given <message> as the commit message.",
)
@click.option(
    "-F",
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Take the commit message from the given file.",
)
@click.option(
    "-e",
    "--edit/--no-edit",
    "edit",
    default=None,
    help="Invoke editor to edit the commit message (or skip with --no-edit).",
)
@click.option(
    "-C",
    "--reuse-message",
    "reuse_message",
    metavar="<commit>",
    type=str,
    help="Reuse the commit message from <commit> without editing.",
)
@click.option(
    "-c",
    "--reedit-message",
    "reedit_message",
    metavar="<commit>",
    type=str,
    help="Reuse the commit message from <commit> and edit it.",
)
@click.option(
    "--amend",
    is_flag=True,
    help="Replace the tip of the current branch by creating a new commit.",
)
@click.pass_context
def commit(
    ctx: click.Context,
    message: Optional[str],
    file_path: Optional[str],
    edit: Optional[bool],
    reuse_message: Optional[str],
    reedit_message: Optional[str],
    amend: bool,
) -> None:
    """Record changes to the repository."""
    message_sources = [
        bool(message),
        bool(file_path),
        bool(reuse_message),
        bool(reedit_message),
    ]
    if sum(message_sources) > 1:
        raise click.UsageError(
            "Options -m/--message, -F/--file, -C/--reuse-message "
            "and -c/--reedit-message are mutually exclusive."
        )

    if (
        edit is not None
        and ctx.params.get("edit") is not None
        and edit != ctx.params["edit"]
    ):
        raise click.UsageError("--edit and --no-edit cannot be used together.")

    cmd_args: list[str] = ["commit"]

    if message:
        cmd_args.extend(["-m", message])
    elif file_path:
        cmd_args.extend(["-F", file_path])
    elif reuse_message:
        cmd_args.extend(["-C", reuse_message])
    elif reedit_message:
        cmd_args.extend(["-c", reedit_message])

    if edit:
        cmd_args.append("-e")
    else:
        cmd_args.append("--no-edit")

    if amend:
        cmd_args.append("--amend")

    run_cmd(*cmd_args)


@cli.command()
@click.option("--porcelain", is_flag=True, help="Machine‑readable output.")
def status(porcelain: bool) -> None:
    """Show the working tree status."""
    run_cmd("status", *("--porcelain",) if porcelain else ())


@cli.command(
    name="diff",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "--cached",
    "--staged",
    "cached",
    is_flag=True,
    help="Compare index with HEAD instead of work‑tree with index.",
)
@click.option(
    "-p",
    "-u",
    "--patch",
    "patch_mode",
    flag_value="patch",
    default=None,
    help="Produce patch (default behaviour).",
)
@click.option(
    "-s",
    "--no-patch",
    "patch_mode",
    flag_value="no_patch",
    help="Suppress patch output (just list files).",
)
@click.option("-1", "--base", "stage", flag_value="1", help="Diff stage 1 (base).")
@click.option("-2", "--ours", "stage", flag_value="2", help="Diff stage 2 (ours).")
@click.option("-3", "--theirs", "stage", flag_value="3", help="Diff stage 3 (theirs).")
@click.argument("rest", nargs=-1, type=click.UNPROCESSED)
def diff_cmd(
    cached: bool,
    patch_mode: Optional[str],
    stage: Optional[str],
    rest: tuple[str, ...],
) -> None:
    """Show changes between commits, commit and working tree, etc."""
    cmd_args: list[str] = []

    if cached:
        cmd_args.append("--cached")

    if patch_mode == "patch":
        cmd_args.append("-p")
    elif patch_mode == "no_patch":
        cmd_args.append("-s")

    if stage == "1":
        cmd_args.append("-1")
    elif stage == "2":
        cmd_args.append("-2")
    elif stage == "3":
        cmd_args.append("-3")

    cmd_args.extend(rest)

    run_cmd("diff", *cmd_args)


@cli.command()
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (-v, -vv, …). Repeat for more detail.",
)
@click.option("-d", "--delete", "delete_flag", is_flag=True, help="Delete the branch")
@click.option(
    "-f", "--force", "force_flag", is_flag=True, help="Force delete / force update"
)
@click.option(
    "-D",
    "D_flag",
    is_flag=True,
    help="Shortcut for --delete --force. Overrides individual -d / -f flags.",
)
@click.option(
    "-a",
    "--all",
    "all_branches_flag",
    is_flag=True,
    help="List both local *and* remote‑tracking branches",
)
@click.option(
    "-r",
    "--remotes",
    "remotes_flag",
    is_flag=True,
    help="Limit listing / actions to remote‑tracking branches",
)
@click.option(
    "--set-upstream-to",
    "-u",
    "upstream",
    metavar="UPSTREAM",
    help="Set branch’s upstream (same as -u)",
)
@click.option(
    "--unset-upstream",
    is_flag=True,
    help="Remove the branch’s upstream configuration",
)
@click.option(
    "-t",
    "--track",
    "track_flag",
    is_flag=True,
    help="When creating <name>, set it to track <start>",
)
@click.argument("name", required=False)
@click.argument("start", required=False)
def branch(
    verbose: int,
    delete_flag: bool,
    force_flag: bool,
    D_flag: bool,
    all_branches_flag: bool,
    remotes_flag: bool,
    upstream: str | None,
    unset_upstream: bool,
    track_flag: bool,
    name: str | None,
    start: str | None,
) -> None:
    """List, create, or delete branches."""
    flags: list[str] = []

    if verbose:
        flags.extend(["-v"] * verbose)

    if D_flag:
        flags.append("-D")
    else:
        if delete_flag:
            flags.append("-d")
        if force_flag:
            flags.append("-f")

    if all_branches_flag:
        flags.append("-a")
    if remotes_flag:
        flags.append("-r")

    if upstream:
        flags.extend(["--set-upstream-to", upstream])
    if unset_upstream:
        flags.append("--unset-upstream")
    if track_flag:
        flags.append("--track")

    args: list[str] = []
    if name:
        args.append(name)
    if start:
        args.append(start)

    run_cmd("branch", *flags, *args)


@cli.command(
    name="log",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "--abbrev-commit/--no-abbrev-commit",
    "abbrev",
    default=None,
    help="Use abbreviated commit hashes.",
)
@click.option(
    "--pretty",
    "--format",
    "format_",
    default="medium",
    metavar="<format>",
    help="Pretty‑print format (e.g. medium, oneline).",
)
@click.option(
    "--oneline",
    is_flag=True,
    help="Shortcut for --pretty=oneline --abbrev-commit.",
)
@click.option(
    "--decorate",
    "decoration",
    type=click.Choice(["short", "full", "no", "auto"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="Decorate refs. 'auto' is default, 'no' disables.",
)
@click.option(
    "-p",
    "-u",
    "--patch",
    "patch_mode",
    flag_value="patch",
    default=None,
    help="Show patch for each commit.",
)
@click.option(
    "-s",
    "--no-patch",
    "patch_mode",
    flag_value="no_patch",
    help="Suppress patch output (like --stat-only).",
)
@click.option(
    "--cc",
    "combined",
    is_flag=True,
    help="Show combined diff format for merge commits (implies --patch).",
)
@click.option(
    "--all", "all_refs", is_flag=True, help="Pretend as if all refs were listed."
)
@click.option(
    "--branches",
    "branches",
    is_flag=True,
    help="Pretend as if all branch refs were listed.",
)
@click.option(
    "--remotes",
    "remotes",
    is_flag=True,
    help="Pretend as if all remote-tracking refs were listed.",
)
@click.argument("rest", nargs=-1, type=click.UNPROCESSED)
def log(
    abbrev: bool | None,
    format_: str,
    oneline: bool,
    decoration: str,
    patch_mode: str | None,
    combined: bool,
    all_refs: bool,
    branches: bool,
    remotes: bool,
    rest: tuple[str, ...],
) -> None:
    """Show commit logs."""
    if oneline:
        format_ = "oneline"
        if abbrev is None:
            abbrev = True

    if combined:
        patch_mode = "patch"

    cmd_args: list[str] = ["log"]

    if abbrev is True:
        cmd_args.append("--abbrev-commit")
    elif abbrev is False:
        cmd_args.append("--no-abbrev-commit")

    if format_ == "oneline":
        cmd_args.append("--oneline")
    elif format_ != "medium":
        cmd_args.append(f"--pretty={format_}")

    if decoration != "auto":
        if decoration == "no":
            cmd_args.append("--no-decorate")
        else:
            cmd_args.append(f"--decorate={decoration}")

    if patch_mode == "patch":
        cmd_args.append("--patch")
    elif patch_mode == "no_patch":
        cmd_args.append("--no-patch")

    if combined:
        cmd_args.append("--cc")

    if all_refs:
        cmd_args.append("--all")
    if branches:
        cmd_args.append("--branches")
    if remotes:
        cmd_args.append("--remotes")

    cmd_args.extend(rest)

    run_cmd(*cmd_args)


@cli.command(
    name="merge",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "-e",
    "--edit/--no-edit",
    "edit",
    default=None,
    help="Edit merge commit message (or skip with --no-edit).",
)
@click.option(
    "-m",
    "--message",
    "message",
    type=str,
    help="Use the given <message> as the commit message.",
)
@click.option(
    "-F",
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Take the commit message from the given file.",
)
@click.option("--continue", "cont", is_flag=True, help="Continue an in‑progress merge.")
@click.option("--abort", "abort", is_flag=True, help="Abort the in‑progress merge.")
@click.argument("refs", nargs=-1)
def merge(
    edit: bool | None,
    message: str | None,
    file_path: str | None,
    cont: bool,
    abort: bool,
    refs: tuple[str, ...],
) -> None:
    """Join two or more development histories together."""
    if message and file_path:
        raise click.UsageError("-m/--message and -F/--file are mutually exclusive.")

    if cont and abort:
        raise click.UsageError("--continue and --abort cannot be used together.")

    if not (cont or abort) and not refs:
        raise click.UsageError("You must specify a branch, tag or commit to merge.")

    cmd_args: list[str] = ["merge"]

    if cont:
        cmd_args.append("--continue")
    elif abort:
        cmd_args.append("--abort")

    if edit is True:
        cmd_args.append("-e")
    elif edit is False:
        cmd_args.append("--no-edit")

    if message:
        cmd_args.extend(["-m", message])
    elif file_path:
        cmd_args.extend(["-F", file_path])

    cmd_args.extend(refs)

    run_cmd(*cmd_args)


@cli.command()
@click.option(
    "-r",
    "recursive",
    is_flag=True,
    help="Remove directories and their contents recursively.",
)
@click.option(
    "--cached", is_flag=True, help="Remove from the index, not from the working tree."
)
@click.option(
    "-f",
    "--force",
    "force",
    is_flag=True,
    help="Ignore nonexistent files and arguments, never prompt.",
)
@click.argument("paths", nargs=-1, required=True)
def rm(recursive: bool, cached: bool, force: bool, paths: tuple[str, ...]) -> None:
    """Remove files from the working tree and from the index."""
    cmd_args = ["rm"]

    if recursive:
        cmd_args.append("-r")
    if cached:
        cmd_args.append("--cached")
    if force:
        cmd_args.append("-f")

    cmd_args.extend(paths)
    run_cmd(*cmd_args)


@cli.command(
    name="config",
    context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.option(
    "--local",
    "file_scope",
    flag_value="local",
    help="Use local repository config file.",
)
@click.option(
    "--global", "file_scope", flag_value="global", help="Use global user config file."
)
@click.option(
    "--system", "file_scope", flag_value="system", help="Use system-wide config file."
)
@click.option(
    "-f", "--file", "file_scope", type=click.Path(), help="Use given config file."
)
@click.option(
    "--add",
    is_flag=True,
    help="Add a new line to the option, without altering existing values.",
)
@click.option(
    "--replace-all",
    is_flag=True,
    help="Replace all lines matching the key, not just the last one.",
)
@click.option("--get-all", is_flag=True, help="Get all values for a multi-valued key.")
@click.option("--unset", is_flag=True, help="Remove the line matching the key.")
@click.option("--unset-all", is_flag=True, help="Remove all lines matching the key.")
@click.option("--remove-section", is_flag=True, help="Remove the entire section.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def config(
    file_scope: str,
    add: bool,
    replace_all: bool,
    get_all: bool,
    unset: bool,
    unset_all: bool,
    remove_section: bool,
    args: list[str],
) -> None:
    """Get and set repository or global options."""
    cmd_args = []

    if file_scope:
        if file_scope in ["local", "global", "system"]:
            cmd_args.append(f"--{file_scope}")
        else:
            cmd_args.extend(["--file", file_scope])

    action_flags = {
        "--add": add,
        "--replace-all": replace_all,
        "--get-all": get_all,
        "--unset": unset,
        "--unset-all": unset_all,
        "--remove-section": remove_section,
    }

    for flag, is_set in action_flags.items():
        if is_set:
            cmd_args.append(flag)
            break

    cmd_args.extend(args)

    run_cmd("config", *cmd_args)


@cli.command(
    name="remote",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Be more verbose and show remote URLs.",
)
@click.option(
    "-t",
    "tracked",
    multiple=True,
    metavar="BRANCH",
    help="Limit the operation to refs that are tracked by <BRANCH>. "
    "May be given more than once.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def remote(
    verbose: bool,
    tracked: tuple[str, ...],
    args: tuple[str, ...],
) -> None:
    """Manage the set of tracked repositories."""
    cmd_args: list[str] = ["remote"]

    if verbose:
        cmd_args.append("--verbose")

    for br in tracked:
        cmd_args.extend(["-t", br])

    cmd_args.extend(args)

    run_cmd(*cmd_args)


@cli.command()
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Force update of local refs (pass --force to the fetch command).",
)
@click.option(
    "--upload-pack",
    "upload_pack",
    metavar="<path>",
    help="Specify the path to the remote upload-pack program.",
)
@click.argument("refs", nargs=-1)
def fetch(force: bool, upload_pack: str | None, refs: tuple[str, ...]) -> None:
    """Download objects and refs from another repository."""
    cmd_args: list[str] = []

    if force:
        cmd_args.append("--force")
    if upload_pack:
        cmd_args.append(f"--upload-pack={upload_pack}")

    cmd_args.extend(refs)

    run_cmd("fetch", *cmd_args)


@cli.command()
@click.option(
    "-f", "--force", "force", is_flag=True, help="Force updates (pass -f to push)."
)
@click.option(
    "--receive-pack",
    "receive_pack",
    metavar="<path>",
    help="Path to the remote receive-pack program.",
)
@click.argument("refs", nargs=-1, metavar="REF")
def push(force: bool, receive_pack: str | None, refs: tuple[str, ...]) -> None:
    """Update remote refs along with associated objects."""
    cmd_args: list[str] = []

    if force:
        cmd_args.append("-f")
    if receive_pack:
        cmd_args.append(f"--receive-pack={receive_pack}")

    cmd_args.extend(refs)

    run_cmd("push", *cmd_args)


@cli.command(name="checkout")
@click.argument("target", metavar="REVISION", required=True)
def checkout(target: str) -> None:
    """Switch branches or restore working‑tree files."""
    run_cmd("checkout", target)


@cli.command(
    name="cherry-pick",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "--continue",
    "cont",
    is_flag=True,
    help="Continue an in‑progress cherry‑pick sequence.",
)
@click.option(
    "--abort", "abort", is_flag=True, help="Abort the current cherry‑pick sequence."
)
@click.option(
    "--quit", "quit_", is_flag=True, help="End the sequence without changing HEAD."
)
@click.option(
    "-m",
    "--mainline",
    "mainline",
    type=int,
    metavar="PARENT",
    help="Pick a merge commit by choosing its <PARENT> as mainline.",
)
@click.option(
    "-e",
    "--edit/--no-edit",
    "edit",
    default=None,
    help="Edit the commit message before creating each picked commit.",
)
@click.option(
    "--message",
    "message",
    type=str,
    metavar="<msg>",
    help="Replace the default commit message with <msg> for all picks.",
)
@click.option(
    "-F",
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    metavar="<file>",
    help="Read the commit message from <file>.",
)
@click.argument("commits", nargs=-1)
def cherry_pick(
    cont: bool,
    abort: bool,
    quit_: bool,
    mainline: int | None,
    edit: bool | None,
    message: str | None,
    file_path: str | None,
    commits: tuple[str, ...],
) -> None:
    """Apply the changes introduced by some existing commits."""
    mode_flags = [cont, abort, quit_]
    if sum(mode_flags) > 1:
        raise click.UsageError("--continue, --abort and --quit are mutually exclusive.")

    if not any(mode_flags) and not commits:
        raise click.UsageError("You must supply at least one commit to cherry‑pick.")

    if message and file_path:
        raise click.UsageError("--message and -F/--file cannot be used together.")

    cmd_args: list[str] = ["cherry-pick"]

    if cont:
        cmd_args.append("--continue")
    elif abort:
        cmd_args.append("--abort")
    elif quit_:
        cmd_args.append("--quit")

    if mainline is not None:
        cmd_args.extend(["-m", str(mainline)])

    if edit is True:
        cmd_args.append("-e")
    elif edit is False:
        cmd_args.append("--no-edit")

    if message:
        cmd_args.append(f"--message={message}")
    elif file_path:
        cmd_args.extend(["-F", file_path])

    cmd_args.extend(commits)

    run_cmd(*cmd_args)


@cli.command(
    name="reset",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "--soft",
    "mode_soft",
    is_flag=True,
    help="Move HEAD to <commit>, keep index and work‑tree unchanged.",
)
@click.option(
    "--mixed",
    "mode_mixed",
    is_flag=True,
    help="Reset index to <commit> (default).",
)
@click.option(
    "--hard",
    "mode_hard",
    is_flag=True,
    help="Reset index and working tree, discarding changes.",
)
@click.argument("targets", nargs=-1, type=click.UNPROCESSED)
def reset(
    mode_soft: bool,
    mode_mixed: bool,
    mode_hard: bool,
    targets: tuple[str, ...],
) -> None:
    """Reset current HEAD to the specified state."""
    if sum([mode_soft, mode_mixed, mode_hard]) > 1:
        raise click.UsageError("--soft, --mixed, and --hard are mutually exclusive.")

    cmd_args: list[str] = ["reset"]

    if mode_soft:
        cmd_args.append("--soft")
    elif mode_hard:
        cmd_args.append("--hard")
    elif mode_mixed:
        cmd_args.append("--mixed")

    cmd_args.extend(targets)

    run_cmd(*cmd_args)


@cli.command(
    name="revert",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "--continue", "cont", is_flag=True, help="Continue an in‑progress revert sequence."
)
@click.option(
    "--abort",
    "abort",
    is_flag=True,
    help="Abort the current revert sequence and restore the index.",
)
@click.option(
    "--quit",
    "quit_",
    is_flag=True,
    help="End the sequence without committing the remaining reverts.",
)
@click.option(
    "-m",
    "--mainline",
    "mainline",
    type=int,
    metavar="PARENT",
    help="When reverting a merge, choose <PARENT> as mainline.",
)
@click.option(
    "-e",
    "--edit/--no-edit",
    "edit",
    default=None,
    help="Edit each generated commit message in an editor.",
)
@click.option(
    "--message",
    "message",
    type=str,
    metavar="<msg>",
    help="Use <msg> as commit message instead of the default.",
)
@click.option(
    "-F",
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    metavar="<file>",
    help="Read the commit message from <file>.",
)
@click.argument("commits", nargs=-1)
def revert(
    cont: bool,
    abort: bool,
    quit_: bool,
    mainline: int | None,
    edit: bool | None,
    message: str | None,
    file_path: str | None,
    commits: tuple[str, ...],
) -> None:
    """Revert the changes introduced by existing commits."""
    if sum([cont, abort, quit_]) > 1:
        raise click.UsageError("--continue, --abort and --quit are mutually exclusive.")
    if not any([cont, abort, quit_]) and not commits:
        raise click.UsageError("You must specify at least one commit to revert.")
    if message and file_path:
        raise click.UsageError("--message and -F/--file cannot be used together.")

    cmd_args: list[str] = ["revert"]

    if cont:
        cmd_args.append("--continue")
    elif abort:
        cmd_args.append("--abort")
    elif quit_:
        cmd_args.append("--quit")

    if mainline is not None:
        cmd_args.extend(["-m", str(mainline)])

    if edit is True:
        cmd_args.append("-e")
    elif edit is False:
        cmd_args.append("--no-edit")

    if message:
        cmd_args.append(f"--message={message}")
    elif file_path:
        cmd_args.extend(["-F", file_path])

    cmd_args.extend(commits)

    run_cmd(*cmd_args)


def _plumbing(ctx: click.Context, cmd_name: str, repo: Path, extra: list[str]) -> None:
    run_cmd(cmd_name, str(repo), *extra)


@cli.command(
    name="upload-pack",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
    help="Internal helper; invoked by legit during fetch.",
)
@click.argument(
    "repo",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
@click.pass_context
def upload_pack(ctx: click.Context, repo: Path) -> None:
    _plumbing(ctx, "upload-pack", repo, ctx.args)


@cli.command(
    name="receive-pack",
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
    },
    help="Internal helper; invoked by legit during push.",
)
@click.argument(
    "repo",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
@click.pass_context
def receive_pack(ctx: click.Context, repo: Path) -> None:
    _plumbing(ctx, "receive-pack", repo, ctx.args)


if __name__ == "__main__":
    cli()
