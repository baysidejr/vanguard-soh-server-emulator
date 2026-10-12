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


CPF_PARM = 0x80
CPF_RETURN = 0x400


def function_params(p, func_index):
    """Parameters of a function export in declaration order (UField Next chain):
    [(name, property class, flags, extra)] where extra is the struct name for
    StructProperty and the raw type-specific bytes otherwise."""
    kids = {i + 1: e for i, e in enumerate(p.exports) if e["outer"] == func_index + 1 and e["size"] > 0}
    info = {}
    for idx, e in kids.items():
        raw = p.raw[e["offset"]:e["offset"] + e["size"]]
        _, nxt, pos = _field_header(raw)
        kind = p.class_name(e["class"])
        if not kind.endswith("Property"):
            continue
        dim, flags = struct.unpack_from("<II", raw, pos)
        _, pos2 = _compact(raw, pos + 8)            # category
        if flags & CPF_NET:
            pos2 += 2
        extra = raw[pos2:]
        if kind == "StructProperty":
            sidx, _ = _compact(extra, 0)
            extra = p.exports[sidx - 1]["name"] if sidx > 0 else p.imports[-sidx - 1][3]
        info[idx] = (e["name"], kind, flags, extra, nxt)
    pointed = {v[4] for v in info.values()}
    order, cur = [], next((i for i in info if i not in pointed), None)
    while cur in info:
        order.append(cur)
        cur = info[cur][4]
    return [info[i][:4] for i in order if info[i][2] & CPF_PARM and not info[i][2] & CPF_RETURN]


def byte_enum_size(p, extra):
    """Number of values of a ByteProperty's enum (0 = plain byte). extra starts
    at the property's Category; net properties then have a u16 RepOffset and
    ByteProperty a compact Enum reference."""
    _, pos = _compact(extra, 0)          # category
    pos += 2                              # RepOffset (CPF_Net)
    enum_ref, _ = _compact(extra, pos)
    if enum_ref <= 0:
        return 0                          # none, or an import (not resolved here)
    e = p.exports[enum_ref - 1]
    raw = p.raw[e["offset"]:e["offset"] + e["size"]]
    _, _, epos = _field_header(raw)
    count, _ = _compact(raw, epos)
    return count


class NetField:
    def __init__(self, name, kind, array_dim=1, prop_class=None, extra=b"", params=None):
        self.name = name
        self.kind = kind              # 'BoolProperty', ..., or 'Function'
        self.array_dim = array_dim
        self.extra = extra
        self.params = params or []    # functions: [(name, kind, flags, extra)] in order
        self.enum_size = 0            # ByteProperty with an enum: number of values
        self.index = None

    def __repr__(self):
        return f"<{self.kind} {self.name} #{self.index}>"

    def writer(self, value):
        """A function w(BitWriter) that serializes value as this property's
        NetSerializeItem: bool 1 bit, int/float 32 bits, byte 8 bits or
        SerializeInt(value, enum size), string = FString bytes."""
        import struct as _s
        from ue2net import compact_index
        k = self.kind
        if k == "BoolProperty":
            return lambda w: w.bit(1 if value else 0)
        if k == "IntProperty":
            return lambda w: w.bits(int(value) & 0xFFFFFFFF, 32)
        if k == "FloatProperty":
            return lambda w: w.bits(_s.unpack("<I", _s.pack("<f", float(value)))[0], 32)
        if k == "ByteProperty":
            if self.enum_size:
                return lambda w: w.serialize_int(int(value), self.enum_size)
            return lambda w: w.bits(int(value) & 0xFF, 8)
        if k == "StrProperty":
            raw = str(value).encode("latin-1", "replace") + bytes(1)
            return lambda w: w.bytes_(compact_index(len(raw)) + raw)
        raise ValueError(f"{self.name}: {k} not supported")


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
                    f = NetField(e["name"], kind, dim, extra=raw[pos + 8:])
                    if kind == "ByteProperty":
                        f.enum_size = byte_enum_size(p, raw[pos + 8:])
                    fields.append(f)
            elif kind == "Function":
                sup, _, _ = _field_header(raw)
                flags = struct.unpack_from("<I", raw, len(raw) - 6)[0]
                if flags & FUNC_NET and not flags & 0xFF000000 and sup == 0:
                    fields.append(NetField(e["name"], "Function",
                                           params=function_params(p, p.exports.index(e))))
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

    def by_index(self, class_name, index):
        for f in self.class_cache(class_name)["all"]:
            if f.index == index:
                return f
        return None

    def props(self, class_name, values):
        """[(rep_index, max_index, writer)] for actor_open_bunch from
        {property name: value}."""
        cache = self.class_cache(class_name)
        out = []
        for name, value in values.items():
            f = self.field(class_name, name)
            if f.array_dim > 1:
                # Static arrays: one entry per element; the element index byte
                # follows the RepIndex (ReceivedBunch reads it when ArrayDim > 1).
                for i, v in enumerate(value):
                    write = f.writer(v)
                    out.append((f.index, cache["max"],
                                lambda w, i=i, write=write: (w.bits(i, 8), write(w))))
            elif f.kind == "NameProperty":
                index, count = self.name_index(value)
                out.append((f.index, cache["max"],
                            lambda w, index=index, count=count: w.serialize_int(index, count + 1)))
            else:
                out.append((f.index, cache["max"], f.writer(value)))
        return out

    def name_index(self, name):
        """FName on the wire (UPackageMapLevel FUN_00b164f0): SerializeInt(index,
        total + 1), index = position in the package map's concatenated name
        tables (packages in USES order); total = None."""
        base = 0
        found = None
        for _, p in self.packages:
            if found is None:
                lowered = [n.lower() for n in p.names]
                if str(name).lower() in lowered:
                    found = base + lowered.index(str(name).lower())
            base += len(p.names)
        if name is None or found is None:
            if name is not None:
                raise KeyError(f"name {name!r} is not in any package of the map")
            return base, base
        return found, base

    def field(self, class_name, field_name):
        for f in self.class_cache(class_name)["all"]:
            if f.name.lower() == field_name.lower():
                return f
        raise KeyError(field_name)
