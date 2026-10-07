"""Exercise metadata-only pruning with synthetic kernel ioctl responses."""

import errno
import importlib.util
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("pruner", sys.argv.pop(1))
pruner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pruner)
REAL_OPEN, REAL_CLOSE, REAL_FSTAT = os.open, os.close, os.fstat


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mount = Path(self.temp.name)
        self.root = self.mount / "@old-roots/archive/root"
        self.root.mkdir(parents=True)
        self.paths = {5: self.mount, 256: self.root}
        self.parents = {256: 5}
        self.flags = {5: 0, 256: 0}
        self.fds = {}
        self.deleted = []
        self.made_writable = []

    def add(self, identity, parent, name):
        path = self.paths[parent] / name
        path.mkdir(parents=True)
        self.paths[identity], self.parents[identity] = path, parent
        self.flags[identity] = 0

    def open(self, path, _flags):
        fd = len(self.fds) + 100
        self.fds[fd] = Path(path)
        return fd

    def ioctl(self, fd, request, data):
        identity = next(key for key, value in self.paths.items() if value == self.fds[fd])
        if request == pruner.GET_INFO:
            struct.pack_into("=Q", data, 0, identity)
        elif request == pruner.FS_INFO:
            data[16:32] = b"F" * 16
        elif request == pruner.GET_FLAGS:
            struct.pack_into("=Q", data, 0, self.flags[identity])
        elif request == pruner.SET_FLAGS:
            self.assertTrue(self.flags[identity] & pruner.READ_ONLY)
            self.flags[identity] = struct.unpack_from("=Q", data)[0]
            self.made_writable.append(identity)
        elif request == pruner.GET_ROOTREF:
            children = [key for key, parent in self.parents.items() if parent == identity]
            if children:
                struct.pack_into("=QQ", data, 8, children[0], 500)
                data[4088] = 1
        elif request == pruner.LOOKUP_USER:
            target = struct.unpack_from("=Q", data, 8)[0]
            path = self.paths[target]
            name = os.fsencode(path.name)
            directory = os.fsencode(str(path.parent.relative_to(self.fds[fd])))
            if directory == b".":
                directory = b""
            else:
                directory += b"/"
            data[16 : 16 + len(name)] = name
            data[272 : 272 + len(directory)] = directory
        else:
            raise AssertionError(f"Unexpected ioctl {request}")

    def delete(self, args, **_kwargs):
        identity = int(args[4])
        self.assertFalse(any(parent == identity for parent in self.parents.values()))
        self.assertFalse(self.flags[self.parents[identity]] & pruner.READ_ONLY)
        self.assertEqual(Path(args[5]), self.mount)
        self.deleted.append(identity)
        with (
            patch.object(os, "open", REAL_OPEN),
            patch.object(os, "close", REAL_CLOSE),
            patch.object(os, "fstat", REAL_FSTAT),
        ):
            shutil.rmtree(self.paths.pop(identity))
        self.parents.pop(identity)

    def run_prune(self, budget):
        with (
            patch.object(pruner.os, "open", side_effect=self.open),
            patch.object(pruner.os, "close"),
            patch.object(pruner.os, "fstat", return_value=SimpleNamespace(st_ino=256)),
            patch.object(pruner.fcntl, "ioctl", side_effect=self.ioctl),
            patch.object(pruner.subprocess, "run", side_effect=self.delete),
        ):
            return pruner.prune(self.mount, self.root, budget)

    def test_budget_covers_nested_deletions_and_resume_keeps_root_until_last(self):
        for index in range(33):
            self.add(257 + index, 256, f"Scratch/build-{index}")
        self.assertEqual(self.run_prune(16), 16)
        self.assertTrue(self.root.is_dir())
        self.assertEqual(self.run_prune(16), 16)
        self.assertTrue(self.root.is_dir())
        self.assertEqual(self.run_prune(16), 2)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.deleted[-1], 256)

    def test_descendants_with_newlines_are_deleted_deepest_first(self):
        self.add(257, 256, "Scratch/a space\nand newline")
        self.add(258, 257, "ordinary directory/nested")
        (self.root / "keep until deletion").write_text("ordinary contents")
        self.assertEqual(self.run_prune(16), 3)
        self.assertEqual(self.deleted, [258, 257, 256])

    def test_no_file_tree_walk_is_needed_for_ordinary_files(self):
        (self.root / "Scratch").mkdir()
        for index in range(100):
            (self.root / "Scratch" / str(index)).write_text("build output")
        self.assertEqual(self.run_prune(1), 1)
        self.assertEqual(self.deleted, [256])

    def test_readonly_ancestors_allow_budgeted_child_deletion_and_resume(self):
        self.add(257, 256, "parent")
        self.add(258, 257, "child")
        for identity in (256, 257, 258):
            self.flags[identity] = pruner.READ_ONLY
        self.assertEqual(self.run_prune(1), 1)
        self.assertEqual(self.deleted, [258])
        self.assertEqual(self.made_writable, [256, 257])
        self.assertTrue(self.flags[258] & pruner.READ_ONLY)
        self.assertTrue(self.root.is_dir())
        self.assertEqual(self.run_prune(16), 2)
        self.assertEqual(self.deleted, [258, 257, 256])
        self.assertFalse(self.root.exists())

    def test_live_root_is_never_a_valid_prune_target(self):
        with self.assertRaisesRegex(ValueError, "Only an archived root"):
            pruner.prune(self.mount, self.mount, 16)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.made_writable, [])

    def test_other_filesystem_is_rejected_before_deletion(self):
        self.flags[256] = pruner.READ_ONLY
        with (
            patch.object(pruner, "filesystem", side_effect=[b"F" * 16, b"other-filesystem"]),
            self.assertRaisesRegex(ValueError, "target filesystem"),
        ):
            self.run_prune(16)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.made_writable, [])

    def test_descendant_cannot_escape_archive(self):
        self.flags[256] = pruner.READ_ONLY
        with (
            patch.object(pruner, "child", return_value=(999, Path("../@persist"))),
            self.assertRaisesRegex(ValueError, "escapes its root"),
        ):
            self.run_prune(16)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.made_writable, [])

    def test_symlink_descendant_is_rejected_before_changing_ancestor_flags(self):
        self.flags[256] = pruner.READ_ONLY
        (self.root / "nested").symlink_to(self.mount, target_is_directory=True)
        with (
            patch.object(pruner, "child", return_value=(999, Path("nested"))),
            self.assertRaisesRegex(ValueError, "follows a symlink"),
        ):
            self.run_prune(16)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.made_writable, [])

    def test_depth_limit_is_checked_before_changing_ancestor_flags(self):
        self.flags[256] = pruner.READ_ONLY
        self.add(257, 256, "nested")
        with (
            patch.object(pruner, "MAX_DEPTH", 1),
            self.assertRaisesRegex(ValueError, "supported depth"),
        ):
            self.run_prune(16)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.made_writable, [])

    def test_rootref_overflow_still_uses_the_returned_batch(self):
        self.add(257, 256, "nested")
        original = self.ioctl

        def overflow(fd, request, data):
            original(fd, request, data)
            if request == pruner.GET_ROOTREF:
                raise OSError(errno.EOVERFLOW, "more metadata available")

        with (
            patch.object(pruner.os, "open", side_effect=self.open),
            patch.object(pruner.os, "close"),
            patch.object(pruner.fcntl, "ioctl", side_effect=overflow),
        ):
            fd = self.open(self.root, 0)
            self.assertEqual(pruner.child(fd), (257, Path("nested")))


unittest.main()
