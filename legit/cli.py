import os
from typing import Optional
import sys
from pathlib import Path

import click

from legit.cmd_base import Base


CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 120,
}

def run_cmd(cmd_name: str, *args: str) -> None:
    from legit.command import Command

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
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), required=False)
def init(path: Path | None) -> None:
    """Create an empty Legit repository in *PATH* (defaults to current dir)."""

    run_cmd("init", *(str(path),) if path is not None else ())


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
def add(paths: tuple[Path, ...]) -> None:
    """Add file contents of *PATHS* to the index (staging area)."""

    # Git treats “legit add” with no paths as an error; here we mimic that.
    if not paths:
        click.echo("error: pathspec required", err=True)
        raise SystemExit(1)

    run_cmd("add", *(str(p) for p in paths))


@cli.command()
@click.option(
    "-m", "--message", "message",
    type=str,
    help="Use the given <message> as the commit message."
)
@click.option(
    "-F", "--file", "file_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Take the commit message from the given file."
)
@click.pass_context
def commit(ctx: click.Context, message: Optional[str], file_path: Optional[str]) -> None:
    """Record changes to the repository."""

    if message and file_path:
        raise click.UsageError("Options -m/--message and -F/--file are mutually exclusive.")

    cmd_args = ["commit"]
    if message:
        cmd_args.extend(["-m", message])
    elif file_path:
        cmd_args.extend(["-F", file_path])
   
    run_cmd(*cmd_args)

@cli.command()
@click.option("--porcelain", is_flag=True, help="Machine‑readable output.")
def status(porcelain: bool) -> None:
    """Show the working tree status."""

    run_cmd("status", *("--porcelain",) if porcelain else ())



@cli.command(name="diff")
@click.option("--cached", "--staged", is_flag=True, help="Compare index with HEAD.")
def diff_cmd(cached: bool) -> None:
    """Show changes between index/HEAD or index/worktree."""

    run_cmd("diff", *("--cached",) if cached else ())


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Show verbose branch output')
@click.option('-d', '--delete', 'delete', is_flag=True, help='Delete a branch')
@click.option('-f', '--force', 'force', is_flag=True, help='Force delete a branch')
@click.option('-D', 'D', is_flag=True, help='Shortcut for --delete --force')
@click.argument('name', required=False)
@click.argument('start', required=False)
def branch(verbose: bool, delete: bool, force: bool, D: bool, name: str | None, start: str | None) -> None:
    """List, create, or delete branches."""
    flags = []
    if verbose:
        flags.append('-v')
    if delete or D:
        flags.append('-d')
    if force or D:
        flags.append('-f')
    if D and not (delete and force):
        # If -D used alone, ensure both delete and force get set
        flags = [f for f in flags if f not in ('-d', '-f')]
        flags.extend(['-D'])
    
    # Build positional args
    args = []
    if name:
        args.append(name)
    if start:
        args.append(start)
    
    run_cmd('branch', *flags, *args)

@cli.command()
@click.argument("target")
def checkout(target: str) -> None:
    """Switch branches or restore files."""

    run_cmd("checkout", target)


@cli.command()
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
    help="Pretty-print format (e.g., medium, oneline).",
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
    "--patch", "-p",
    "patch",
    is_flag=True,
    help="Show patch for each commit.",
)
@click.argument("revisions_and_paths", nargs=-1)
def log(abbrev: bool | None, format_: str, oneline: bool, decoration: str, patch: bool, revisions_and_paths: tuple[str, ...]):
    """Display commit history."""
    
    if oneline:
        format_ = "oneline"
        if abbrev is None:
            abbrev = True

    cmd_args = ["log"]

    if abbrev is True:
        cmd_args.append("--abbrev-commit")
    elif abbrev is False:
        cmd_args.append("--no-abbrev-commit")

    if format_ != "medium":
        if format_ == "oneline":
             cmd_args.append("--oneline")
        else:
             cmd_args.append(f"--pretty={format_}")
    
    if decoration != "auto":
        if decoration == "no":
            cmd_args.append("--no-decorate")
        else:
            cmd_args.append(f"--decorate={decoration}")

    if patch:
        cmd_args.append("--patch")
    
    if revisions_and_paths:
        cmd_args.extend(revisions_and_paths)

    run_cmd(*cmd_args)

@cli.command()
@click.argument("refs", nargs=-1)
def merge(refs: tuple[str, ...]) -> None:
    """Join two or more development histories together."""
    cmd_args = ["merge"]
    cmd_args.extend(refs)
    run_cmd(*cmd_args)

@cli.command()
@click.option(
    "-r",
    "recursive",
    is_flag=True,
    help="Remove directories and their contents recursively."
)
@click.option(
    "--cached",
    is_flag=True,
    help="Remove from the index, not from the working tree."
)
@click.option(
    "-f",
    "--force",
    "force",
    is_flag=True,
    help="Ignore nonexistent files and arguments, never prompt."
)
@click.argument("paths", nargs=-1, required=True)
def rm(recursive: bool, cached: bool, force: bool, paths: tuple[str, ...]) -> None:
    """
    Remove files or directories.

    By default, `rm` removes paths from both the working tree and index.
    """
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
@click.option("--local", "file_scope", flag_value="local", help="Use local repository config file.")
@click.option("--global", "file_scope", flag_value="global", help="Use global user config file.")
@click.option("--system", "file_scope", flag_value="system", help="Use system-wide config file.")
@click.option("-f", "--file", "file_scope", type=click.Path(), help="Use given config file.")
@click.option("--add", is_flag=True, help="Add a new line to the option, without altering existing values.")
@click.option("--replace-all", is_flag=True, help="Replace all lines matching the key, not just the last one.")
@click.option("--get-all", is_flag=True, help="Get all values for a multi-valued key.")
@click.option("--unset", is_flag=True, help="Remove the line matching the key.")
@click.option("--unset-all", is_flag=True, help="Remove all lines matching the key.")
@click.option("--remove-section", is_flag=True, help="Remove the entire section.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def config(file_scope, add, replace_all, get_all, unset, unset_all, remove_section, args):
    """Get and set repository or global options."""
    
    cmd_args = []

    # Handle file scope options
    if file_scope:
        if file_scope in ["local", "global", "system"]:
            cmd_args.append(f"--{file_scope}")
        else:
            cmd_args.extend(["--file", file_scope])

    # Handle action flags
    action_flags = {
        "--add": add,
        "--replace-all": replace_all,
        "--get-all": get_all,
        "--unset": unset,
        "--unset-all": unset_all,
        "--remove-section": remove_section,
    }

    # Add the action flag that was used (if any) to the arguments
    for flag, is_set in action_flags.items():
        if is_set:
            cmd_args.append(flag)
            break # Assume only one action flag can be used at a time

    # Add the remaining positional arguments (key, value, etc.)
    cmd_args.extend(args)
    
    run_cmd("config", *cmd_args)

@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Be more verbose and show remote URLs.')
@click.argument("args", nargs=-1)
def remote(verbose: bool, args: tuple[str, ...]) -> None:
    """
    Manage the set of tracked repositories.
    
    Subcommands:
        add <name> <url>      Adds a remote
        remove <name>         Removes a remote
    """
    cmd_args = []
    
    # The first positional argument is the subcommand (e.g., 'add')
    subcommand = args[0] if args else None
    
    # Pass along any top-level flags like --verbose
    if verbose:
        cmd_args.append('--verbose')

    if subcommand:
        cmd_args.append(subcommand)
        # Pass the rest of the arguments (e.g., the name and url)
        cmd_args.extend(args[1:])
        
    run_cmd("remote", *cmd_args)


@cli.command()
@click.option(
    "-f", "--force",
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
    """
    Download objects and refs from another repository.
    """
    cmd_args: list[str] = []

    if force:
        cmd_args.append("--force")
    if upload_pack:
        cmd_args.append(f"--upload-pack={upload_pack}")

    # any remaining positional refs (e.g. <remote> <refspec>…)
    cmd_args.extend(refs)

    run_cmd("fetch", *cmd_args)


@cli.command()
@click.option(
    '-f', '--force',
    'force',
    is_flag=True,
    help='Force updates (pass -f to push).'
)
@click.option(
    '--receive-pack',
    'receive_pack',
    metavar='<path>',
    help='Path to the remote receive-pack program.'
)
@click.argument('refs', nargs=-1, metavar='REF')
def push(force: bool, receive_pack: str | None, refs: tuple[str, ...]) -> None:
    """
    Update remote refs along with associated objects.
    """
    cmd_args: list[str] = []

    # translate our click flags into legit’s push flags
    if force:
        cmd_args.append('-f')
    if receive_pack:
        cmd_args.append(f'--receive-pack={receive_pack}')

    # any remaining positional refs (e.g. <remote> <refspec>…)
    cmd_args.extend(refs)

    run_cmd('push', *cmd_args)


if __name__ == '__main__':
    cli()
