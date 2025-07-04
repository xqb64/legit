from legit.cmd_base import Base
from legit.remotes import Remotes


class Remote(Base):
    def define_options(self) -> None:
        self.options = {"verbose": False, "tracked": []}
        positional_args = []

        args_iter = iter(self.args)
        for arg in args_iter:
            if arg in ("-v", "--verbose"):
                self.options["verbose"] = True
            elif arg == "-t":
                try:
                    self.options["tracked"].append(next(args_iter))
                except StopIteration:
                    pass
            else:
                positional_args.append(arg)

        self.args = positional_args

    def run(self) -> None:
        self.define_options()
        try:
            cmd = self.args.pop(0)
        except IndexError:
            cmd = None
        match cmd:
            case c if c == "add":
                self.add_remote()
            case c if c == "remove":
                self.remove_remote()
            case _:
                self.list_remotes()

    def add_remote(self) -> None:
        name, url = self.args[0], self.args[1]
        try:
            self.repo.remotes.add(name, url, self.options["tracked"])
            self.exit(0)
        except Remotes.InvalidRemote as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

    def remove_remote(self) -> None:
        try:
            self.repo.remotes.remove(self.args[0])
            self.exit(0)
        except Remotes.InvalidRemote as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

    def list_remotes(self) -> None:
        for name in self.repo.remotes.list_remotes():
            self.list_remote(name)
        self.exit(0)

    def list_remote(self, name: str) -> None:
        if not self.options["verbose"]:
            self.println(name)
            return

        remote = self.repo.remotes.get(name)

        self.println(f"{name}\t{remote.fetch_url} (fetch)")
        self.println(f"{name}\t{remote.push_url} (push)")
