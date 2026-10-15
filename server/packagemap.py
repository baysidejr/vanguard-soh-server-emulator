"""The UE2 package map the server announces to the client.

Before WELCOME the server sends one control-channel line per package:

    USES GUID=<32 hex> PKG=<name> FLAGS=<flags> SIZE=<bytes> GEN=<generation> FNAME=<file>

The client's UNetPendingLevel::NotifyReceivedText (FUN_009677e0) appends each to
its UPackageMap; WELCOME then checks that every package exists locally with that
GUID. Object references in bunches (UPackageMapLevel::SerializeObject,
FUN_00953ad0) are then one bit (1 = actor by channel index, 0 = object) and, for
objects, SerializeInt(index, MaxObjectIndex), where an object's index is the
export counts of all earlier packages plus its own export index.
"""

import os

from upackage import Package

# Packages announced, in order. Index numbering depends on this order.
DEFAULT_PACKAGES = ["Core", "Engine", "SGOUnrealAbstractionLayer"]


def fx_packages(client_dir):
    """The FX* packages among the client's own ServerPackages (bin/sysconfig.ini), in order.
    The client loads only the packages the server announces, and effects such as the loot
    sparkle (FXspells) and quest-node particles (FXmystical) find their emitter class by
    name among loaded packages, so these follow the defaults (after them, so the indices of
    everything before stay the same)."""
    out = []
    try:
        with open(os.path.join(client_dir, "bin", "sysconfig.ini"), encoding="utf-8", errors="replace") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "ServerPackages" and value.startswith("FX") and value not in out and                         os.path.exists(os.path.join(client_dir, "UnrealScript", value + ".u")):
                    out.append(value)
    except OSError:
        pass
    return out


def find_map(client_dir, level):
    """Path of a level package (<level>.vgr) in the client's map folder."""
    maps = os.path.join(client_dir, "Assets", "Maps")
    for f in os.listdir(maps):
        if f.lower() == level.lower() + ".vgr":
            return os.path.join(maps, f)
    raise FileNotFoundError(f"{level}.vgr not in {maps}")


class PackageMap:
    """The level package must come first: on WELCOME the client loads the map
    from package-map entry 0 (a Core-first map made it look for 'Level
    Core.MyLevel' and quit with a version-mismatch error)."""

    def __init__(self, client_dir, level, names=None):
        if names is None:
            names = DEFAULT_PACKAGES + fx_packages(client_dir)
        level_path = find_map(client_dir, level)
        self.packages = [(level, Package(level_path), os.path.basename(level_path))]
        for name in names:
            path = os.path.join(client_dir, "UnrealScript", name + ".u")
            self.packages.append((name, Package(path), name + ".u"))

    @property
    def max_object_index(self):
        return sum(len(p.exports) for _, p, _ in self.packages)

    def uses_lines(self):
        lines = []
        for name, p, fname in self.packages:
            lines.append(f"USES GUID={p.guid_text} PKG={name} FLAGS={p.flags} SIZE={p.size} "
                         f"GEN={len(p.generations)} FNAME={fname}")
        return lines

    def object_index(self, path):
        """Net index of 'Package.Object' (an export directly inside the package)."""
        cache = self.__dict__.setdefault("_object_index_cache", {})
        if path not in cache:
            cache[path] = self._object_index(path)
        return cache[path]

    def _object_index(self, path):
        pkg_name, obj_name = path.split(".", 1)
        base = 0
        for name, p, _ in self.packages:
            if name.lower() == pkg_name.lower():
                i = p.find_export(obj_name, "Class")
                if i is None:
                    i = p.find_export(obj_name)
                if i is None:
                    raise KeyError(path)
                return base + i
            base += len(p.exports)
        raise KeyError(pkg_name)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    pm = PackageMap(os.path.join(here, ".."), "Entry")
    for line in pm.uses_lines():
        print(line)
    print("MaxObjectIndex", pm.max_object_index)
    for cls in ("Engine.PlayerController", "Engine.Pawn", "SGOUnrealAbstractionLayer.SGOPCPawn"):
        print(cls, pm.object_index(cls))
