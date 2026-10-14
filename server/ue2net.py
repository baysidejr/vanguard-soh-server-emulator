"""Unreal Engine 2 network packets as used by the Vanguard client.

The client's in-world traffic is UE2 UNetConnection packets, carried inside the
zone server's UdpLibrary connection as zone message type 1 (u16 1, u32 length,
packet bytes). Field widths come from the client's UNetConnection::ReceivedPacket
(FUN_0095f230) and match a captured client HELLO:

    PacketId        SerializeInt(32768)  15 bits
    per item:
      IsAck         1 bit
      ack:          AckPacketId  SerializeInt(32768)
      bunch:        bControl, [bOpen, bClose if control], bReliable,
                    ChIndex      SerializeInt(1024)   10 bits
                    ChSequence   SerializeInt(4096)   12 bits  (if reliable)
                    ChType       SerializeInt(8)       3 bits  (if reliable or open)
                    DataBits     SerializeInt(4096)   12 bits  (MaxPacket 512 * 8)
                    data
    terminator: a single 1 bit, then zero padding to the byte

Bits are packed LSB-first. Control-channel messages are FStrings: a compact-index
length (including the NUL) followed by 8-bit characters and a NUL.
"""

MAX_PACKETID = 32768
MAX_CHANNELS = 1024
MAX_CHSEQUENCE = 4096
CHTYPE_MAX = 8
MAX_BUNCH_BITS = 512 * 8

CHTYPE_CONTROL = 1
CHTYPE_ACTOR = 2
CHTYPE_FILE = 3


class BitReader:
    def __init__(self, data):
        if not data or data[-1] == 0:
            raise ValueError("packet missing trailing 1 bit")
        self.data = data
        self.end = (len(data) - 1) * 8 + data[-1].bit_length() - 1
        self.pos = 0

    def left(self):
        return self.end - self.pos

    def bit(self):
        if self.pos >= self.end:
            raise ValueError("read past end of packet")
        b = (self.data[self.pos >> 3] >> (self.pos & 7)) & 1
        self.pos += 1
        return b

    def bits(self, n):
        v = 0
        for i in range(n):
            v |= self.bit() << i
        return v

    def serialize_int(self, value_max):
        v, mask = 0, 1
        while v + mask < value_max and mask:
            if self.bit():
                v |= mask
            mask <<= 1
        return v


class BitWriter:
    def __init__(self):
        self.bitlist = []

    def bit(self, b):
        self.bitlist.append(1 if b else 0)

    def bits(self, value, n):
        for i in range(n):
            self.bit((value >> i) & 1)

    def serialize_int(self, value, value_max):
        mask = 1
        new_value = 0
        while new_value + mask < value_max and mask:
            if value & mask:
                self.bit(1)
                new_value |= mask
            else:
                self.bit(0)
            mask <<= 1

    def bytes_(self, data):
        for byte in data:
            self.bits(byte, 8)

    def packed(self):
        """(bytes, bit count) without a terminator, for bunch payloads."""
        out = bytearray((len(self.bitlist) + 7) // 8)
        for i, b in enumerate(self.bitlist):
            if b:
                out[i >> 3] |= 1 << (i & 7)
        return bytes(out), len(self.bitlist)

    def vector(self, v):
        """FVector::SerializeCompressed (client reader FUN_00962170)."""
        ints = [int(round(c)) for c in v]
        biggest = max(abs(i) for i in ints)
        # appCeilLogTwo(1 + biggest), clamped to 1..20, minus one
        n = 1 + biggest
        ceil_log2 = (n - 1).bit_length()
        bits = max(1, min(20, ceil_log2)) - 1
        self.serialize_int(bits, 20)
        bias = 1 << (bits + 1)
        top = 1 << (bits + 2)
        for i in ints:
            self.serialize_int(i + bias, top)

    def rotator(self, r):
        """FRotator::SerializeCompressed (FUN_00960d40): per component a flag bit,
        then the top byte if non-zero."""
        for c in r:
            b = (int(c) >> 8) & 0xFF
            self.bit(1 if b else 0)
            if b:
                self.bits(b, 8)

    def finish(self):
        """Terminator bit, then pad to a whole byte."""
        bits = self.bitlist + [1]
        out = bytearray((len(bits) + 7) // 8)
        for i, b in enumerate(bits):
            if b:
                out[i >> 3] |= 1 << (i & 7)
        return bytes(out)


def compact_index(value):
    """UE2 FCompactIndex: sign + 6 bits, then 7 bits per byte."""
    neg = value < 0
    v = abs(value)
    first = (0x80 if neg else 0) | (v & 0x3F)
    v >>= 6
    if v:
        first |= 0x40
    out = bytearray([first])
    while v:
        b = v & 0x7F
        v >>= 7
        if v:
            b |= 0x80
        out.append(b)
    return bytes(out)


def read_compact_index(data, pos):
    b = data[pos]
    pos += 1
    neg = b & 0x80
    v = b & 0x3F
    shift = 6
    more = b & 0x40
    while more:
        b = data[pos]
        pos += 1
        v |= (b & 0x7F) << shift
        shift += 7
        more = b & 0x80
    return (-v if neg else v), pos


def fstring(text):
    raw = text.encode("latin-1") + b"\0"
    return compact_index(len(raw)) + raw


def read_fstrings(data):
    """Split a control bunch's bytes into the FStrings it carries."""
    out, pos = [], 0
    while pos < len(data):
        n, pos = read_compact_index(data, pos)
        if n < 0:  # UTF-16 string
            raw = data[pos:pos - n * 2]
            pos += -n * 2
            out.append(raw.decode("utf-16-le", "replace").rstrip("\0"))
        else:
            raw = data[pos:pos + n]
            pos += n
            out.append(raw.decode("latin-1", "replace").rstrip("\0"))
    return out


class Bunch:
    def __init__(self, channel, data, reliable=True, control=False, open_=False, close=False,
                 ch_type=CHTYPE_CONTROL, seq=0, nbits=None):
        self.channel = channel
        self.data = data
        self.nbits = len(data) * 8 if nbits is None else nbits
        self.reliable = reliable
        self.control = control
        self.open = open_
        self.close = close
        self.ch_type = ch_type
        self.seq = seq

    def __repr__(self):
        flags = "".join(c for c, f in (("C", self.control), ("O", self.open), ("X", self.close),
                                       ("R", self.reliable)) if f)
        return f"<Bunch ch={self.channel} {flags} seq={self.seq} type={self.ch_type} {len(self.data)}B>"


def decode_packet(data):
    """Return (packet_id, acks, bunches). Bunch data is returned as bytes when its bit
    count is a multiple of 8 (control text always is), else as raw bits."""
    r = BitReader(data)
    packet_id = r.serialize_int(MAX_PACKETID)
    acks, bunches = [], []
    while r.left() > 0:
        if r.bit():
            acks.append(r.serialize_int(MAX_PACKETID))
            continue
        control = r.bit()
        open_ = close = 0
        if control:
            open_, close = r.bit(), r.bit()
        reliable = r.bit()
        channel = r.serialize_int(MAX_CHANNELS)
        seq = r.serialize_int(MAX_CHSEQUENCE) if reliable else 0
        ch_type = r.serialize_int(CHTYPE_MAX) if (reliable or open_) else 0
        nbits = r.serialize_int(MAX_BUNCH_BITS)
        payload = bytes(r.bits(8) for _ in range(nbits // 8))
        rest = nbits % 8
        if rest:
            payload += bytes([r.bits(rest)])
        bunches.append(Bunch(channel, payload, bool(reliable), bool(control), bool(open_),
                             bool(close), ch_type, seq, nbits))
    return packet_id, acks, bunches


def seq_diff(a, b, modulus):
    """a - b for sequence numbers that wrap at modulus (UE2 BestSignedDifference)."""
    return ((a - b + modulus // 2) % modulus) - modulus // 2


def encode_packet(packet_id, acks=(), bunches=()):
    w = BitWriter()
    w.serialize_int(packet_id, MAX_PACKETID)
    for ack in acks:
        w.bit(1)
        w.serialize_int(ack, MAX_PACKETID)
    for b in bunches:
        w.bit(0)
        w.bit(b.control)
        if b.control:
            w.bit(b.open)
            w.bit(b.close)
        w.bit(b.reliable)
        w.serialize_int(b.channel, MAX_CHANNELS)
        if b.reliable:
            w.serialize_int(b.seq, MAX_CHSEQUENCE)
        if b.reliable or b.open:
            w.serialize_int(b.ch_type, CHTYPE_MAX)
        w.serialize_int(b.nbits, MAX_BUNCH_BITS)
        for i in range(b.nbits):
            w.bit((b.data[i >> 3] >> (i & 7)) & 1)
    return w.finish()


class UnrealSession:
    """Server side of one client's UE2 connection: packet ids, acks, and the
    reliable sequence on each channel."""

    def __init__(self):
        self.out_packet_id = 0
        self.out_reliable = {}   # channel -> last sequence sent
        self.in_reliable = {}    # channel -> last sequence received
        self.pending_acks = []

    def receive(self, data):
        packet_id, acks, bunches = decode_packet(data)
        self.pending_acks.append(packet_id)
        fresh = []
        for b in bunches:
            if b.reliable:
                if seq_diff(b.seq, self.in_reliable.get(b.channel, 0), MAX_CHSEQUENCE) <= 0:
                    continue  # resend of something already handled (wrap-aware: 4095 -> 0)
                self.in_reliable[b.channel] = b.seq
            fresh.append(b)
        return packet_id, acks, fresh

    def control_bunch(self, *texts):
        seq = self.out_reliable.get(0, 0) + 1
        self.out_reliable[0] = seq
        data = b"".join(fstring(t) for t in texts)
        return Bunch(0, data, reliable=True, control=True, ch_type=CHTYPE_CONTROL, seq=seq)

    def actor_open_bunch(self, channel, class_index, max_object_index, location=(0, 0, 0),
                         rotation=None, extra=None, properties=()):
        """Open an actor channel and spawn an actor of the given class on the client
        (UActorChannel::ReceivedBunch, FUN_00964ab0). Payload: object reference
        (bit 0 = not an actor channel, then SerializeInt(class, MaxObjectIndex)),
        compressed location, rotation if the class has bNetInitialRotation, and
        for Pawn subclasses Vanguard's extra byte + 2 u32s. Properties follow;
        properties is a list of (rep_index, max_index, write) where write(w)
        serializes the value (see netcache.py for indices)."""
        w = BitWriter()
        w.bit(0)
        w.serialize_int(class_index, max_object_index)
        w.vector(location)
        if rotation is not None:
            w.rotator(rotation)
        if extra is not None:
            byte, a, b = extra
            w.bits(byte, 8)
            w.bits(a & 0xFFFFFFFF, 32)
            w.bits(b & 0xFFFFFFFF, 32)
        for rep_index, max_index, write in properties:
            w.serialize_int(rep_index, max_index)
            write(w)
        data, nbits = w.packed()
        seq = self.out_reliable.get(channel, 0) + 1
        self.out_reliable[channel] = seq
        return Bunch(channel, data, reliable=True, control=True, open_=True,
                     ch_type=CHTYPE_ACTOR, seq=seq, nbits=nbits)

    def actor_close_bunch(self, channel):
        """Close an actor channel: the client destroys the actor (bClose is only
        read on control bunches)."""
        seq = self.out_reliable.get(channel, 0) + 1
        self.out_reliable[channel] = seq
        return Bunch(channel, b"", reliable=True, control=True, close=True,
                     ch_type=CHTYPE_ACTOR, seq=seq)

    def actor_bunch(self, channel, data=b"", nbits=0):
        """A reliable bunch on an already-open actor channel (properties/RPCs)."""
        seq = self.out_reliable.get(channel, 0) + 1
        self.out_reliable[channel] = seq
        return Bunch(channel, data, reliable=True, ch_type=CHTYPE_ACTOR, seq=seq, nbits=nbits)

    def build(self, bunches=()):
        """One outgoing packet carrying pending acks and the given bunches."""
        pkt = encode_packet(self.out_packet_id, self.pending_acks, bunches)
        self.out_packet_id = (self.out_packet_id + 1) % MAX_PACKETID
        self.pending_acks = []
        return pkt


if __name__ == "__main__":
    # Self-test against the HELLO captured from the real client.
    hello = bytes.fromhex("00000b400004274c908a98989e40a48aac92a6929e9c7a60409a929cac8aa47a"
                          "66626a6240ac8aa47a6662706c0002")
    pid, acks, bunches = decode_packet(hello)
    assert pid == 0 and not acks and len(bunches) == 1, (pid, acks, bunches)
    b = bunches[0]
    assert (b.channel, b.control, b.open, b.reliable, b.seq, b.ch_type) == (0, True, True, True, 1, 1)
    assert read_fstrings(b.data) == ["HELLO REVISION=0 MINVER=3151 VER=3186"], read_fstrings(b.data)
    assert encode_packet(0, [], [b]) == hello, "re-encode mismatch"
    print("ue2net self-test passed:", read_fstrings(b.data)[0])
