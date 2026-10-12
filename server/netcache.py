"""Replication field indices (UE2 FClassNetCache) computed from the client's packages.

A property or RPC in an actor bunch is identified by SerializeInt(RepIndex,
MaxIndex). The client (UPackageMap::GetClassNetCache, FUN_00b18180) numbers a
class's NetFields after its superclass's: RepIndex = FieldsBase + position.
NetFields are the class's own properties with CPF_Net and its replicated
functions (FUNC_Net) that don't override a superclass function, in the
order of the package's export table (verified live: Actor field 11 decoded as
DrawType, which is 11th in export order; name order would be bNetOwner).

Vanguard differs from stock UE2 in one important way: Actor.bNetOwner is a
replicated property. The client adopts a PlayerController as its own
(UNetConnection::HandleClientPlayer) only when that bit is set after a bunch
(UActorChannel::ReceivedBunch, FUN_00964ab0).
"""

import struct

from upackage import _compact

CPF_NET = 0x20
FUNC_NET = 0x40


def _field_header(raw):
    """(SuperField, Next) of a serialized UField."""
    pos = 0
    _, pos = _compact(raw, pos)       # tagged-property terminator ("None")
    sup, pos = _compact(raw, pos)
    nxt, pos = _compact(raw, pos)
    return sup, nxt, pos


class NetField:
    def __init__(self, name, kind, array_dim=1, prop_class=None, extra=b""):
        self.name = name
        self.kind = kind              # 'BoolProperty', ..., or 'Function'
        self.array_dim = array_dim
        self.extra = extra
        self.index = None

    def __repr__(self):
        return f"<{self.kind} {self.name} #{self.index}>"


class NetCache:
    def __init__(self, packages):
        """packages: list of (name, Package) in package-map order."""
        self.packages = packages
        self._cache = {}

    def _find_class(self, name):
        for pkg_name, p in self.packages:
            i = p.find_export(name, "Class")
            if i is not None:
                return pkg_name, p, i
        raise KeyError(name)

    def _own_net_fields(self, p, cls_index):
        data = p.raw
        fields = []
        for e in p.exports:
            if e["outer"] != cls_index + 1 or e["size"] <= 0:
                continue
            kind = p.class_name(e["class"])
            raw = data[e["offset"]:e["offset"] + e["size"]]
            if kind.endswith("Property"):
                sup, nxt, pos = _field_header(raw)
                dim, flags = struct.unpack_from("<II", raw, pos)
                if flags & CPF_NET:
                    fields.append(NetField(e["name"], kind, dim, extra=raw[pos + 8:]))
            elif kind == "Function":
                sup, _, _ = _field_header(raw)
                flags = struct.unpack_from("<I", raw, len(raw) - 6)[0]
                if flags & FUNC_NET and not flags & 0xFF000000 and sup == 0:
                    fields.append(NetField(e["name"], "Function"))
        return fields

    def class_cache(self, name):
        """[(NetField...)], fields_base, max_index for a class name."""
        if name in self._cache:
            return self._cache[name]
        pkg_name, p, i = self._find_class(name)
        sup = p.exports[i]["super"]
        if sup == 0:
            base_fields, base = [], 0
        else:
            sup_name = p.exports[sup - 1]["name"] if sup > 0 else p.imports[-sup - 1][3]
            try:
                parent = self.class_cache(sup_name)
                base_fields, base = parent["all"], parent["max"]
            except KeyError:
                base_fields, base = [], 0   # e.g. Core.Object, not announced or no net fields
        own = self._own_net_fields(p, i)
        for n, f in enumerate(own):
            f.index = base + n
        result = {"own": own, "all": base_fields + own, "base": base, "max": base + len(own)}
        self._cache[name] = result
        return result

    def field(self, class_name, field_name):
        for f in self.class_cache(class_name)["all"]:
            if f.name.lower() == field_name.lower():
                return f
        raise KeyError(field_name)
