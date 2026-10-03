"""Budgeted archived-root deletion using Btrfs metadata, never a file-tree walk."""

import errno
import fcntl
import os
import struct
import subprocess
import sys
from pathlib import Path

# Linux UAPI: btrfs_ioctl_get_subvol_info_args (504 bytes), rootref (4096),
# and ino_lookup_user (4096). The workstation supports x86_64 Linux only.
GET_INFO = 0x81F8943C
GET_ROOTREF = 0xD000943D
LOOKUP_USER = 0xD000943E
FS_INFO = 0x8400941F
GET_FLAGS = 0x80089419
SET_FLAGS = 0x4008941A
READ_ONLY = 1 << 1
MAX_DEPTH = 64
MAX_LOOKUPS = 256


def info(fd):
    data = bytearray(504)
    fcntl.ioctl(fd, GET_INFO, data)
    return struct.unpack_from("=Q", data)[0]


def filesystem(fd):
    data = bytearray(1024)
    fcntl.ioctl(fd, FS_INFO, data)
    return data[16:32]


def make_writable(fd):
    flags = bytearray(8)
    fcntl.ioctl(fd, GET_FLAGS, flags)
    value = struct.unpack_from("=Q", flags)[0]
    if value & READ_ONLY:
        struct.pack_into("=Q", flags, 0, value & ~READ_ONLY)
        fcntl.ioctl(fd, SET_FLAGS, flags)


def child(fd):
    data = bytearray(4096)
    try:
        fcntl.ioctl(fd, GET_ROOTREF, data)
    except OSError as error:
        # EOVERFLOW means this batch contains 255 entries. Only the first is
        # needed; subsequent runs query remaining children after deletion.
        if error.errno != errno.EOVERFLOW:
            raise
    if not data[4088]:
        return None
    treeid, dirid = struct.unpack_from("=QQ", data, 8)
    lookup = bytearray(4096)
    struct.pack_into("=QQ", lookup, 0, dirid, treeid)
    fcntl.ioctl(fd, LOOKUP_USER, lookup)
    name = os.fsdecode(bytes(lookup[16:272]).split(b"\0", 1)[0])
    directory = os.fsdecode(bytes(lookup[272:]).split(b"\0", 1)[0])
    path = Path(directory) / name
    if not name or name in (".", "..") or "/" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError("Invalid Btrfs descendant path")
    return treeid, path


def prune(mount, root, budget):
    if root.is_symlink():
        raise ValueError("Archive root must not be a symlink")
    mount, root = mount.resolve(), root.resolve()
    if not root.is_relative_to(mount / "@old-roots") or root.name != "root":
        raise ValueError("Only an archived root may be pruned")
    mount_fd = os.open(mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if info(mount_fd) != 5:
            raise ValueError("Pruning requires a top-level Btrfs mount")
        fsid = filesystem(mount_fd)
    finally:
        os.close(mount_fd)
    stack = [(root, None)]
    removed = 0
    for _ in range(MAX_LOOKUPS):
        if not stack or removed >= budget:
            break
        path, expected = stack[-1]
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if os.fstat(fd).st_ino != 256 or filesystem(fd) != fsid:
                raise ValueError("Archive descendant is not a subvolume on the target filesystem")
            treeid = info(fd)
            if expected is not None and treeid != expected:
                raise ValueError("Archive descendant identity changed")
            descendant = child(fd)
            if descendant:
                identity, relative = descendant
                target = path / relative
                if target.resolve() != target or not target.is_relative_to(root):
                    raise ValueError("Archive descendant escapes its root or follows a symlink")
                if len(stack) >= MAX_DEPTH:
                    raise ValueError("Archive subvolume nesting exceeds the supported depth")
                # Deleting a child requires a writable parent, even by ID.
                # Change only the validated archive ancestor through its fd.
                make_writable(fd)
        finally:
            os.close(fd)
        if descendant:
            stack.append((target, identity))
        else:
            subprocess.run(
                ["btrfs", "subvolume", "delete", "--subvolid", str(treeid), str(mount)],
                check=True,
                stdout=sys.stderr,
            )
            removed += 1
            stack.pop()
    return removed


if __name__ == "__main__":
    limit = int(sys.argv[3])
    if not 1 <= limit <= 16:
        raise ValueError("Prune budget must be between 1 and 16")
    print(prune(Path(sys.argv[1]), Path(sys.argv[2]), limit))
