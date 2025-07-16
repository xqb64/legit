# legit

This is a Python implementation of the git clone found in James Coglan's amazing book.

## Usage

```
(env) [alex@arcticbox ~/src/legit]$ legit --help
Usage: legit [OPTIONS] COMMAND [ARGS]...

Options:
  -h, --help  Show this message and exit.

Commands:
  add           Add file contents to the index.
  branch        List, create, or delete branches.
  checkout      Switch branches or restore working‑tree files.
  cherry-pick   Apply the changes introduced by some existing commits.
  commit        Record changes to the repository.
  config        Get and set repository or global options.
  diff          Show changes between commits, commit and working tree, etc.
  fetch         Download objects and refs from another repository.
  init          Create an empty legit repository or reinitialize an existing one.
  log           Show commit logs.
  merge         Join two or more development histories together.
  push          Update remote refs along with associated objects.
  receive-pack  Internal helper; invoked by legit during push.
  remote        Manage the set of tracked repositories.
  reset         Reset current HEAD to the specified state.
  revert        Revert the changes introduced by existing commits.
  rm            Remove files from the working tree and from the index.
  status        Show the working tree status.
  upload-pack   Internal helper; invoked by legit during fetch.
  ```

## Installation

```
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt .
```

## Tests

Make sure you have dev requirements installed, then run:

```
pytest
```

## License

Licensed under the MIT license.
