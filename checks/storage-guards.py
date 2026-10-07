"""Verify production installer guards against the disposable VM's storage."""

import json
import sys

import install as installer

stage = sys.argv[1]
devices = ("/dev/vdc", "/dev/vdd")
inventory = {disk["name"]: disk for disk in installer.disk_inventory()}
reasons = {device: installer.blocked_reason(inventory[device]) for device in devices}

if stage == "mounted-btrfs":
    raw = json.loads(
        installer.run(
            "lsblk", "--json", "--paths", "--output", "NAME,MOUNTPOINTS", *devices, capture=True
        )
    )["blockdevices"]
    secondary = next(disk for disk in raw if disk["name"] == devices[1])
    assert not any(secondary.get("mountpoints") or []), secondary
    assert all(reason == "member of a mounted Btrfs filesystem" for reason in reasons.values()), (
        reasons
    )
elif stage == "unmounted-btrfs":
    assert all(reason is None for reason in reasons.values()), reasons
elif stage == "inactive-lvm":
    assert all(
        isinstance(reason, str) and "LVM2_member" in reason and "other disks" in reason
        for reason in reasons.values()
    ), reasons
else:
    raise ValueError(f"Unknown storage fixture stage: {stage}")

print(stage, json.dumps(reasons))
