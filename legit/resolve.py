from pathlib import Path
from legit.blob import Blob
from legit.repository import Repository
from legit.inputs import Inputs
from legit.tree import DatabaseEntry
from legit.diff3 import Diff3


class Resolve:
    def __init__(self, repo: Repository, inputs: Inputs) -> None:
        self.repo: Repository = repo
        self.inputs: Inputs = inputs
        self._on_progress = lambda message: None

    def execute(self) -> None:
        self.prepare_tree_diffs()
        migration = self.repo.migration(self.clean_diff)
        migration.apply_changes()
        self.add_conflicts_to_index()
        self.write_untracked_files()

    def on_progress(self, block):
        self._on_progress = block

    def log(self, message: str) -> None:
        self._on_progress(message)

    def write_untracked_files(self) -> None:
        for path, item in self.untracked.items():
            blob = self.repo.database.load(item.oid)
            self.repo.workspace.write_file(path, blob.data)

    def add_conflicts_to_index(self) -> None:
        for path, items in self.conflicts.items():
            self.repo.index.add_conflict_set(path, items)

    def prepare_tree_diffs(self) -> None:
        self.untracked = {}

        base_oid = self.inputs.base_oids[0]
        self.left_diff = self.repo.database.tree_diff(base_oid, self.inputs.left_oid)
        self.right_diff = self.repo.database.tree_diff(base_oid, self.inputs.right_oid)
        self.clean_diff = {}
        self.conflicts = {}

        for path, (old_item, new_item) in self.right_diff.items():
            if new_item is not None:
                self.file_dir_conflict(path, self.left_diff, self.inputs.left_name)
            self.same_path_conflict(path, old_item, new_item)

        for path, (old_item, new_item) in self.left_diff.items():
            if new_item is not None:
                self.file_dir_conflict(path, self.right_diff, self.inputs.right_name)

    def file_dir_conflict(self, path, diff, name: str) -> None:
        for parent in path.parents:
            old_item, new_item = diff.get(parent, (None, None))
            if not new_item:
                continue

            if name == self.inputs.left_name:
                self.conflicts[parent] = [old_item, new_item, None]
            elif name == self.inputs.right_name:
                self.conflicts[parent] = [old_item, None, new_item]

            if parent in self.clean_diff:
                del self.clean_diff[parent]

            rename = f"{parent}~{name}"
            self.untracked[rename] = new_item

            if diff.get(path) is None:
                self.log(f"Adding {path}")

            self.log_conflict(parent, rename)

    def same_path_conflict(
        self, path: Path, base: DatabaseEntry, right: DatabaseEntry
    ) -> None:
        if path in self.conflicts:
            return

        if path not in self.left_diff:
            self.clean_diff[path] = [base, right]
            return

        left = self.left_diff[path][1]
        if left == right:
            return

        if left is not None and right is not None:
            self.log(f"Auto-merging {path}")

        oid_ok, oid = self.merge_blobs(
            base.oid if base is not None else None,
            left.oid if left is not None else None,
            right.oid if right is not None else None,
        )

        mode_ok, mode = self.merge_modes(
            base.mode if base is not None else None,
            left.mode if left is not None else None,
            right.mode if right is not None else None,
        )

        self.clean_diff[path] = [left, DatabaseEntry(oid, mode)]
        if oid_ok and mode_ok:
            return

        self.conflicts[path] = [base, left, right]
        self.log_conflict(path)

    def log_conflict(self, path, rename: str | None = None) -> None:
        base, left, right = self.conflicts[path]

        if left and right:
            self.log_left_right_conflict(path)
        elif base and (left or right):
            self.log_modify_delete_conflict(path, rename)
        else:
            self.log_file_directory_conflict(path, rename)

    def log_left_right_conflict(self, path: Path) -> None:
        ty = "content" if self.conflicts[path][0] else "add/add"
        self.log(f"CONFLICT ({ty}): Merge conflict in {path}")

    def log_modify_delete_conflict(self, path: Path, rename: str | None) -> None:
        deleted, modified = self.log_branch_names(path)
        rename = f" at {rename}" if rename is not None else ""

        self.log(
            f"CONFLICT (modify/delete): {path} "
            + f"deleted in {deleted} and modified in {modified}. "
            + f"Version {modified} of {path} left in tree{rename}."
        )

    def log_file_directory_conflict(self, path: Path, rename: str | None) -> None:
        ty = "file/directory" if self.conflicts[path][1] else "directory/file"
        branch, _ = self.log_branch_names(path)

        self.log(
            f"CONFLICT ({ty}): There is a directory "
            + f"with name {path} in {branch}. "
            + f"Adding {path} as {rename}"
        )

    def log_branch_names(self, path: Path) -> tuple[str, str]:
        a, b = self.inputs.left_name, self.inputs.right_name
        return (b, a) if self.conflicts[path][1] else (a, b)

    def merge_blobs(self, base_oid, left_oid, right_oid):
        result = self.merge3(base_oid, left_oid, right_oid)
        if result is not None:
            return result

        oids = [base_oid, left_oid, right_oid]
        blobs = [
            self.repo.database.load(oid).data if oid is not None else "" for oid in oids
        ]
        merge = Diff3.merge(*blobs)

        data = merge.to_string(self.inputs.left_name, self.inputs.right_name)

        blob = Blob(data)
        self.repo.database.store(blob)

        return [merge.is_clean(), blob.oid]

    def merged_data(self, left_oid, right_oid):
        left_blob = self.repo.database.load(left_oid)
        right_blob = self.repo.database.load(right_oid)

        return "".join(
            [
                f"<<<<<<< {self.inputs.left_name}\n",
                left_blob.data,
                "=======\n",
                right_blob.data,
                f">>>>>>> {self.inputs.right_name}\n",
            ]
        )

    def merge_modes(self, base_mode, left_mode, right_mode):
        result = self.merge3(base_mode, left_mode, right_mode)
        if result is not None:
            return result
        return [False, left_mode]

    def merge3(self, base, left, right):
        if left is None:
            return [False, right]

        if right is None:
            return [False, left]

        if left == base or left == right:
            return [True, right]
        elif right == base:
            return [True, left]

        return None
