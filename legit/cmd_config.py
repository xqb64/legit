from __future__ import annotations

from typing import Callable, Optional, Tuple, cast

from legit.cmd_base import Base
from legit.config import ConfigFile, ConfigValue, Conflict, ParseError
from legit.config_stack import ConfigStack


class Config(Base):
    def define_options(self) -> None:
        self.options: dict[str, Optional[str]] = {
            "file": None,
            "add": None,
            "replace": None,
            "get_all": None,
            "unset": None,
            "unset_all": None,
            "remove_section": None,
        }
        args_iter = iter(self.args)
        positional_args = []
        for arg in args_iter:
            if arg == "--local":
                self.options["file"] = "local"
            elif arg == "--global":
                self.options["file"] = "global"
            elif arg == "--system":
                self.options["file"] = "system"
            elif arg.startswith("--file="):
                self.options["file"] = arg.split("=", 1)[1]
            elif arg == "-f":
                try:
                    self.options["file"] = next(args_iter)
                except StopIteration:
                    self.stderr.write("error: flag -f needs a value\n")
                    self.exit(129)
            elif arg == "--add":
                self.options["add"] = next(args_iter, None)
            elif arg == "--replace-all":
                self.options["replace"] = next(args_iter, None)
            elif arg == "--get-all":
                self.options["get_all"] = next(args_iter, None)
            elif arg == "--unset":
                self.options["unset"] = next(args_iter, None)
            elif arg == "--unset-all":
                self.options["unset_all"] = next(args_iter, None)
            elif arg == "--remove-section":
                self.options["remove_section"] = next(args_iter, None)
            elif not arg.startswith("-"):
                positional_args.append(arg)

        self.args = positional_args

    def run(self) -> None:
        self.define_options()
        try:
            if self.options["add"]:
                self._add_variable()
            elif self.options["replace"]:
                self._replace_variable()
            elif self.options["get_all"]:
                self._get_all_values()
            elif self.options["unset"]:
                self._unset_single()
            elif self.options["unset_all"]:
                self._unset_all()
            elif self.options["remove_section"]:
                self._remove_section()
            else:
                if not self.args:
                    self.stderr.write("error: you must specify a key\n")
                    self.exit(2)

                key = self._parse_key(self.args[0])
                value = self.args[1] if len(self.args) > 1 else None

                if value is not None:
                    self._edit_config(lambda config: config.set(key, value))
                else:
                    self._read_config(lambda config: config.get(key))

        except ParseError as e:
            self.stderr.write(f"error: {e}\n")
            self.exit(3)

    def _add_variable(self) -> None:
        key = self._parse_key(self.options["add"])
        self._edit_config(lambda config: config.add(key, self.args[0]))

    def _replace_variable(self) -> None:
        key = self._parse_key(self.options["replace"])
        self._edit_config(lambda config: config.replace_all(key, self.args[0]))

    def _unset_single(self) -> None:
        key = self._parse_key(self.options["unset"])
        self._edit_config(lambda config: config.unset(key))

    def _unset_all(self) -> None:
        key = self._parse_key(self.options["unset_all"])
        self._edit_config(lambda config: config.unset_all(key))

    def _remove_section(self) -> None:
        key = cast(str, self.options["remove_section"]).split(".", 1)
        self._edit_config(lambda config: config.remove_section(key))

    def _get_all_values(self) -> None:
        key = self._parse_key(self.options["get_all"])
        self._read_config(lambda config: config.get_all(key))

    def _read_config(
        self,
        operation: Callable[
            [ConfigFile | ConfigStack], ConfigValue | None | list[ConfigValue]
        ],
    ) -> None:
        config: ConfigFile | ConfigStack = self.repo.config
        if self.options["file"]:
            config = cast(ConfigStack, config).file(self.options["file"])

        config.open()

        result = operation(config)

        if result is None:
            self.exit(1)

        assert result is not None

        values = result if isinstance(result, list) else [result]

        if not values or values == [None]:
            self.exit(1)

        for value in values:
            self.println(str(value))
        self.exit(0)

    def _edit_config(self, operation: Callable[[ConfigFile], bool | None]) -> None:
        file_scope = self.options.get("file") or "local"
        config = self.repo.config.file(file_scope)

        try:
            config.open_for_update()
            operation(config)
            config.save()
            self.exit(0)
        except Conflict as e:
            self.stderr.write(f"error: {e}\n")
            self.exit(5)

    def _parse_key(self, name: Optional[str]) -> Tuple[str, ...]:
        parts = cast(str, name).split(".")

        if len(parts) < 2:
            self.stderr.write(f"error: key does not contain a section: {name}\n")
            self.exit(2)

        section, *subsection, var = parts

        key_for_validation = (section, var)
        if not ConfigFile.valid_key(key_for_validation):
            self.stderr.write(f"error: invalid key: {name}\n")
            self.exit(1)

        if not subsection:
            return section, var
        else:
            return section, ".".join(subsection), var
