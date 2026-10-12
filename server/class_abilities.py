"""Starting abilities per class, taken from the client's own ability visuals.

Each adventuring class has a package Assets/Abilities/<PREFIX>_ABILITIES.aby whose
Ability exports are named <PREFIX>_ABILITIES_<id> and end with a tag such as
"BLADE_WINTER_I". The id is what zone event 0x3d1 plays (see combat.py). The
gameplay data (costs, damage, levels) lived on the server and is not in the
client, so names come from the tags and the numbers are placeholders."""
import os

from upackage import Package

CLASS_PREFIX = {
    0x1C: "WAR", 0x04: "PAL", 0x14: "DRK", 0x13: "RNG", 0x15: "ROG", 0x02: "BRD",
    0x0F: "MNK", 0x1B: "DSC", 0x05: "CLR", 0x16: "SHM", 0x07: "DRU", 0x19: "SOR",
    0x2D: "NEC", 0x0E: "PSI", 0x2C: "BMG",
}

# Tags for effect parts (loops, ticks, procs...) rather than abilities a player uses.
# Spells come as _CAST/_RESOLVE pairs; the resolve part is kept (it carries the impact).
_SKIP = ("LOOP", "TICK", "PROC", "ONSET", "BUFF", "_CAST", "PET_", "_DT_", "_OT_", "_IMPACT",
         "FEEDBACK", "DEBUG", "TEST")

# Generic hotbar icons (iconsTK.xml numbers) used in turn.
_ICONS = [553, 692, 607, 560, 553, 692]

_cache = {}


def ability_tag(data):
    """The FString at the end of an Ability export (compact length + chars + NUL)."""
    for k in range(len(data) - 2, 0, -1):
        if data[k] == len(data) - k - 1 and data[-1] == 0:
            return data[k + 1:-1].decode("latin-1")
    return ""


def package_abilities(client_dir, prefix):
    """[(id, tag)] in export order for <prefix>_ABILITIES.aby."""
    key = (client_dir, prefix)
    if key not in _cache:
        path = os.path.join(client_dir, "Assets", "Abilities", f"{prefix}_ABILITIES.aby")
        out = []
        if os.path.exists(path):
            p = Package(path)
            for e in p.exports:
                try:
                    aid = int(e["name"].rsplit("_", 1)[1])
                except ValueError:
                    continue
                out.append((aid, ability_tag(p.raw[e["offset"]:e["offset"] + e["size"]])))
        _cache[key] = sorted(out)
    return _cache[key]


def display_name(tag):
    """BLADE_WINTER_I -> "Blade Winter I"."""
    words = [w for w in tag.split("_") if w.upper() not in ("RESOLVE", "CAST")]
    return " ".join(w if w in ("I", "II", "III", "IV", "V") else w.capitalize() for w in words)


def class_ability_list(client_dir, klass):
    """[(ability id, tag)] of a class's rank-I abilities, in package order."""
    prefix = CLASS_PREFIX.get(klass)
    if not prefix:
        return []
    picked, names = [], set()
    for aid, tag in package_abilities(client_dir, prefix):
        up = tag.upper()
        if up.endswith("_I") and not any(s in up for s in _SKIP) and display_name(tag) not in names:
            picked.append((aid, tag))
            names.add(display_name(tag))
    return picked


def ability_tuple(n, aid, tag):
    """DEFAULT_ABILITIES-style tuple for the n-th ability of a class."""
    return (n + 1, aid, display_name(tag), _ICONS[n % len(_ICONS)],
            f"{display_name(tag)}.", 0.0 if n == 0 else 5.0 * min(n, 6))


def starting_abilities(client_dir, klass, count=4, learned=()):
    """DEFAULT_ABILITIES-style tuples (handle, ability id, name, icon, description,
    refresh seconds) for the class plus the ones learned from trainers, or [] if
    its package is missing."""
    return [ability_tuple(n, aid, tag) for n, (aid, tag) in enumerate(class_ability_list(client_dir, klass))
            if n < count or aid in learned]


def trainable(client_dir, klass, learned, count=4, offered=6):
    """Trainer offers [(n, ability id, tag, cost copper)]: the next abilities the
    character doesn't know yet (placeholder costs: 1 silver per step)."""
    out = []
    for n, (aid, tag) in enumerate(class_ability_list(client_dir, klass)):
        if n >= count and aid not in learned and len(out) < offered:
            out.append((n, aid, tag, 100 * (n - count + 1)))
    return out


if __name__ == "__main__":
    import races_classes
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    for k in CLASS_PREFIX:
        print(races_classes.class_name(k), [a[2] for a in starting_abilities(here, k)])
