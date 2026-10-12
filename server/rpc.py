"""Decode replicated function calls (RPCs) the client sends on actor channels.

Bunch payload: SerializeInt(RepIndex, MaxIndex) selects the function (see
netcache.py), then each parameter in declaration order: a bool is one bit;
any other parameter is a "present" bit followed, when set, by its value
(UE2 UActorChannel/ProcessRemoteFunction). Verified live with
PlayerController.ShortServerMove(TimeStamp, ClientLoc, ...).
"""

import struct


class BitReader:
    def __init__(self, data, nbits):
        self.data, self.nbits, self.pos = data, nbits, 0

    def bit(self):
        if self.pos >= self.nbits:
            raise ValueError("RPC read past end of bunch")
        v = (self.data[self.pos >> 3] >> (self.pos & 7)) & 1
        self.pos += 1
        return v

    def bits(self, n):
        return sum(self.bit() << i for i in range(n))

    def serialize_int(self, value_max):
        v, mask = 0, 1
        while v + mask < value_max and mask:
            if self.bit():
                v |= mask
            mask <<= 1
        return v


def read_vector(r):
    """FVector::SerializeCompressed (integer coordinates)."""
    bits = r.serialize_int(20)
    bias, top = 1 << (bits + 1), 1 << (bits + 2)
    return tuple(r.serialize_int(top) - bias for _ in range(3))


def read_rotator(r):
    return tuple((r.bits(8) << 8) if r.bit() else 0 for _ in range(3))


def read_value(r, kind, extra, max_object_index):
    if kind == "FloatProperty":
        return struct.unpack("<f", struct.pack("<I", r.bits(32)))[0]
    if kind == "IntProperty":
        v = r.bits(32)
        return v - (1 << 32) if v & 0x80000000 else v
    if kind == "ByteProperty":
        return r.bits(8)
    if kind == "StructProperty":
        if extra == "Rotator":
            return read_rotator(r)
        if extra == "Vector":
            return read_vector(r)
        raise ValueError(f"struct {extra} not supported")
    if kind == "ObjectProperty" or kind == "ClassProperty":
        if r.bit():
            return ("actor", r.serialize_int(1024))
        return ("object", r.serialize_int(max_object_index))
    raise ValueError(f"{kind} not supported")


def decode_rpc(net_cache, class_name, data, nbits, max_object_index):
    """(function name, {param: value}) for one client RPC bunch."""
    r = BitReader(data, nbits)
    cache = net_cache.class_cache(class_name)
    index = r.serialize_int(cache["max"])
    field = net_cache.by_index(class_name, index)
    if field is None or field.kind != "Function":
        return (f"#{index}", {})
    args = {}
    for name, kind, flags, extra in field.params:
        if kind == "BoolProperty":
            args[name] = bool(r.bit())
        elif r.bit():
            args[name] = read_value(r, kind, extra, max_object_index)
    return field.name, args


def encode_rpc(net_cache, class_name, function, values):
    """(data, nbits) of a server->client RPC bunch: RepIndex, then per parameter
    a present bit + value (bools are just their bit). values: {param: value};
    missing parameters are sent as absent."""
    import ue2net
    cache = net_cache.class_cache(class_name)
    field = net_cache.field(class_name, function)
    w = ue2net.BitWriter()
    w.serialize_int(field.index, cache["max"])
    for name, kind, flags, extra in field.params:
        v = values.get(name)
        if kind == "BoolProperty":
            w.bit(1 if v else 0)
            continue
        if v is None:
            w.bit(0)
            continue
        w.bit(1)
        if kind == "FloatProperty":
            w.bits(struct.unpack("<I", struct.pack("<f", float(v)))[0], 32)
        elif kind == "IntProperty":
            w.bits(int(v) & 0xFFFFFFFF, 32)
        elif kind == "ByteProperty":
            w.bits(int(v) & 0xFF, 8)
        elif kind == "StructProperty" and extra == "Rotator":
            w.rotator(v)
        elif kind == "StructProperty" and extra == "Vector":
            w.vector(v)
        else:
            raise ValueError(f"{name}: {kind} not supported")
    return w.packed()
