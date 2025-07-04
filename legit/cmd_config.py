import sys
from typing import List, Tuple, Any, Callable

from legit.cmd_base import Base
from legit.repository import Repository
from legit.config import ConfigFile, ParseError, Conflict

class Config(Base):
    """
    Command for getting and setting repository or global options.
    """

    def __init__(self, *args: List[str]):
        super().__init__(*args)
        self.options = {
            'file': None,
            'add': None,
            'replace': None,
            'get_all': None,
            'unset': None,
            'unset_all': None,
            'remove_section': None,
        }
        self.define_options()

    def define_options(self) -> None:
        """Parses command-line options."""
        args_iter = iter(self.args)
        # Separate positional args from options
        positional_args = []
        for arg in args_iter:
            if arg == "--local":
                self.options['file'] = 'local'
            elif arg == "--global":
                self.options['file'] = 'global'
            elif arg == "--system":
                self.options['file'] = 'system'
            elif arg.startswith("--file="):
                self.options['file'] = arg.split('=', 1)[1]
            elif arg == "-f":
                 try:
                    self.options['file'] = next(args_iter)
                 except StopIteration:
                    self.stderr.write("error: flag -f needs a value\n")
                    self.exit(129) # Exit code for incorrect usage
            elif arg == "--add":
                self.options['add'] = next(args_iter, None)
            elif arg == "--replace-all":
                self.options['replace'] = next(args_iter, None)
            elif arg == "--get-all":
                self.options['get_all'] = next(args_iter, None)
            elif arg == "--unset":
                self.options['unset'] = next(args_iter, None)
            elif arg == "--unset-all":
                self.options['unset_all'] = next(args_iter, None)
            elif arg == "--remove-section":
                self.options['remove_section'] = next(args_iter, None)
            elif not arg.startswith('-'):
                positional_args.append(arg)
        
        self.args = positional_args


    def run(self) -> None:
        """Main execution logic for the config command."""
        try:
            if self.options['add']:
                self._add_variable()
            elif self.options['replace']:
                self._replace_variable()
            elif self.options['get_all']:
                self._get_all_values()
            elif self.options['unset']:
                self._unset_single()
            elif self.options['unset_all']:
                self._unset_all()
            elif self.options['remove_section']:
                self._remove_section()
            else:
                if not self.args:
                    self.stderr.write("error: you must specify a key\n")
                    self.exit(2)

                key = self._parse_key(self.args[0])
                value = self.args[1] if len(self.args) > 1 else None

                if value is not None:
                    # Set a key-value pair
                    self._edit_config(lambda config: config.set(key, value))
                else:
                    # Get a key's value
                    self._read_config(lambda config: config.get(key))

        except ParseError as e:
            self.stderr.write(f"error: {e}\n")
            self.exit(3)

    def _add_variable(self) -> None:
        key = self._parse_key(self.options['add'])
        self._edit_config(lambda config: config.add(key, self.args[0]))

    def _replace_variable(self) -> None:
        key = self._parse_key(self.options['replace'])
        self._edit_config(lambda config: config.replace_all(key, self.args[0]))

    def _unset_single(self) -> None:
        key = self._parse_key(self.options['unset'])
        self._edit_config(lambda config: config.unset(key))

    def _unset_all(self) -> None:
        key = self._parse_key(self.options['unset_all'])
        self._edit_config(lambda config: config.unset_all(key))

    def _remove_section(self) -> None:
        key = self.options['remove_section'].split('.', 1)
        self._edit_config(lambda config: config.remove_section(key))

    def _get_all_values(self) -> None:
        key = self._parse_key(self.options['get_all'])
        self._read_config(lambda config: config.get_all(key))

    def _read_config(self, operation: Callable[[ConfigFile], List[Any]]) -> None:
        """Handles read-only configuration operations."""
        config = self.repo.config
        if self.options['file']:
            config = config.file(self.options['file'])

        config.open()
      
        result = operation(config)

        if result is None:
            self.exit(1)

        values = result if isinstance(result, list) else [result]
        
        if not values or values == [None]:
            self.exit(1)

        for value in values:
            self.println(str(value))
        self.exit(0)

    def _edit_config(self, operation: Callable[[ConfigFile], None]) -> None:
        """Handles write operations on the configuration."""
        # Default to local scope for edits if not specified
        file_scope = self.options.get('file') or 'local'
        config = self.repo.config.file(file_scope)
        
        try:
            config.open_for_update()
            operation(config)
            config.save()
            self.exit(0)
        except Conflict as e:
            self.stderr.write(f"error: {e}\n")
            self.exit(5)

    def _parse_key(self, name: str) -> Tuple[str, ...]:
        """Parses and validates a configuration key string."""
        parts = name.split('.')
        
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

