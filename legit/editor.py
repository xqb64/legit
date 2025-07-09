import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional, Callable


class Editor:
    DEFAULT_EDITOR = "vi"

    def __init__(self, path: os.PathLike, command: Optional[str] = None):
        self.path = Path(path)
        self.command = command or self.DEFAULT_EDITOR
        self._closed = False
        self._file = None
        self.cleaned_content: Optional[str] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._edit_file()

    @classmethod
    def edit(
        cls,
        path: os.PathLike,
        command: Optional[str] = None,
        *,
        block: Callable[["Editor"], None],
    ) -> Optional[str]:
        editor = cls(path, command)

        if block:
            block(editor)

        editor._edit_file()

        return editor.cleaned_content

    def _get_file(self):
        if self._file is None:
            self._file = self.path.open("w", encoding="utf-8")
        return self._file

    def println(self, text: str):
        if not self._closed:
            self._get_file().write(f"{text}\n")

    def note(self, text: str):
        if not self._closed:
            file = self._get_file()
            for line in text.splitlines():
                file.write(f"# {line}\n")

    def close(self):
        self._closed = True

    def _edit_file(self):
        if self._file and not self._file.closed:
            self._file.close()
        if not self._closed:
            editor_argv = shlex.split(self.command) + [str(self.path)]
            try:
                result = subprocess.run(editor_argv)
                if result.returncode != 0:
                    raise RuntimeError(f"Editor exited with a non-zero status.")
            except (FileNotFoundError, RuntimeError) as e:
                raise IOError(
                    f"There was a problem with the editor '{self.command}'."
                ) from e
        try:
            final_text = self.path.read_text(encoding="utf-8")
            self.cleaned_content = self._remove_notes(final_text)
        except FileNotFoundError:
            self.cleaned_content = None

    def _remove_notes(self, text: str) -> Optional[str]:
        lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        if not any(line.strip() for line in lines):
            return None
        return "\n".join(lines).strip() + "\n"
