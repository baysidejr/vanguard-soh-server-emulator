"""SOE UdpLibrary transport, as the Vanguard client speaks it (docs/PROTOCOL.md "Transport").

Cooked packets: 00 01 connect / 00 02 confirm, 00 09 reliable (u16be seq) and 00 0d fragments
(u32be total length in the first), 00 15 AckAll / 00 11 Ack, 00 03 Multi and 00 19 Group
containers. The server keeps every reliable packet until it is acknowledged and resends it
(send_message, resend_tick); client packets are delivered in order with fragments joined
(receive_reliable). Moved out of login_stub.py; login_stub imports everything from here."""
import collections
import struct
import time

PROTOCOL_VERSION = 3
MAX_RAW_PACKET = 1460
MIN_RAW_PACKET = 64       # a smaller claimed size would leave no room for data (endless fragmenting)


def read_group_length(data, pos):
    # Group/varint length (FUN_00bf5e80); assumed SOE style: 1 byte, or 0xff + u16be.
    if data[pos] != 0xFF:
        return data[pos], pos + 1
    if pos + 3 > len(data):
        return 0, len(data)             # truncated length: nothing more in this packet
    return struct.unpack_from(">H", data, pos + 1)[0], pos + 3


def build_confirm(connect_code, max_raw):
    return struct.pack(
        ">BBIIBBBII",
        0x00, 0x02,
        connect_code,
        0,  # encryptCode
        0,  # crcBytes: no CRC on later packets
        0,  # encryptMethod1: none
        0,  # encryptMethod2: none
        min(max_raw, MAX_RAW_PACKET),
        PROTOCOL_VERSION,
    )


def build_reliable(seq, payload):
    # Reliable1: 00 09 | u16be sequence | payload
    return struct.pack(">BBH", 0x00, 0x09, seq & 0xFFFF) + payload   # u16 on the wire: wraps


def build_reliable_fragments(start_seq, payload, max_raw):
    # Fragment1: 00 0d | u16be seq | (first only) u32be total length | data
    # Reassembled by FUN_00c04480.
    packets = []
    seq = start_seq
    pos = 0
    first = True
    while pos < len(payload):
        header = struct.pack(">BBH", 0x00, 0x0D, seq & 0xFFFF)
        if first:
            header += struct.pack(">I", len(payload))
        room = max(1, max_raw - len(header))
        packets.append(header + payload[pos:pos + room])
        pos += room
        seq += 1
        first = False
    return packets, seq


def build_ack_all(channel_type, seq):
    # AckAll1..4 = 0x15..0x18: 00 15 | u16be seq, acknowledges everything up
    # to and including seq on that reliable channel (FUN_00c05730).
    return struct.pack(">BBH", 0x00, 0x15 + (channel_type - 0x09), seq)


def app_messages(payload):
    """Split a reliable payload into application messages. The client bundles
    several messages in a Group (00 19, 1-byte lengths) or Multi (00 03)."""
    if len(payload) >= 2 and payload[0] == 0 and payload[1] in (0x03, 0x19):
        pos = 2
        while pos < len(payload):
            if payload[1] == 0x19:
                n, pos = read_group_length(payload, pos)
            else:
                n, pos = payload[pos], pos + 1
            yield from app_messages(payload[pos:pos + n])
            pos += n
    else:
        yield payload


MAX_REORDER = 512    # reliable packets held while waiting for a missing earlier one


def receive_reliable(sock, addr, state, kind, seq, payload, quiet=False):
    """The application messages that become deliverable with this reliable packet or fragment.
    UdpLibrary delivers in order: a packet after a gap waits (and gets an Ack1, so the client
    resends the missing one at once), resends of delivered packets are only acknowledged again,
    and fragments (00 0d: u32 total length in the first) are joined into one message."""
    expect = state.setdefault("in_expect", seq)
    ahead = (seq - expect) & 0xFFFF
    out = []
    if ahead < 0x8000 and ahead <= MAX_REORDER:
        pending = state.setdefault("in_pending", {})
        pending.setdefault(seq, (kind, payload))
        if ahead:
            sock.sendto(struct.pack(">BBH", 0, 0x11, seq), addr)
            RECEIVE_GAPS[0] += 1
        while expect in pending:
            k, data = pending.pop(expect)
            expect = (expect + 1) & 0xFFFF
            if 0x0D <= k <= 0x10:
                frag = state.get("in_frag")
                if frag is None:
                    if len(data) < 4:
                        continue
                    frag = [struct.unpack_from(">I", data, 0)[0], bytearray(data[4:])]
                else:
                    frag[1] += data
                if len(frag[1]) >= frag[0]:
                    out.extend(app_messages(bytes(frag[1][:frag[0]])))
                    frag = None
                state["in_frag"] = frag
            else:
                out.extend(app_messages(data))
        state["in_expect"] = expect
    ack = build_ack_all(0x09, (expect - 1) & 0xFFFF)
    sock.sendto(ack, addr)
    if not quiet:
        print(f"  <- sent ack-all seq={(expect - 1) & 0xFFFF}: {ack.hex(' ')}")
    return out


def reliable_messages(data):
    """Yield (type, seq, payload) for every Reliable packet and Fragment, including ones
    bundled inside Multi (0x03) or Group (0x19) containers."""
    if len(data) < 2 or data[0] != 0:
        return
    kind = data[1]
    if 0x09 <= kind <= 0x10 and len(data) >= 4:
        yield kind, struct.unpack_from(">H", data, 2)[0], data[4:]
    elif kind == 0x03:
        pos = 2
        while pos < len(data):
            n = data[pos]
            yield from reliable_messages(data[pos + 1:pos + 1 + n])
            pos += 1 + n
    elif kind == 0x19:
        pos = 2
        while pos < len(data):
            n, pos = read_group_length(data, pos)
            yield from reliable_messages(data[pos:pos + n])
            pos += n


def send_message(sock, addr, state, message):
    """Send one application message reliably, fragmenting when it doesn't fit. Each packet is
    kept until the client acknowledges it, and resent if it doesn't (resend_tick)."""
    start = state["out_seq"]
    if len(message) + 4 <= state["max_raw"]:
        packets = [build_reliable(start, message)]
        state["out_seq"] += 1
    else:
        packets, state["out_seq"] = build_reliable_fragments(start, message, state["max_raw"])
    unacked = state.get("unacked")
    if unacked is None:
        import collections
        unacked = state["unacked"] = collections.OrderedDict()
    now = time.time()
    for i, pkt in enumerate(packets):
        unacked[start + i] = [pkt, now, 0, now]        # packet, last sent, resends, first sent
        try:
            sock.sendto(pkt, addr)
        except (BlockingIOError, ConnectionResetError):
            SEND_FAILURES[0] += 1      # the send buffer is full: resend_tick sends it again
    state["sock"], state["addr"] = sock, addr
    if len(unacked) > MAX_UNACKED:
        # A client that stopped acknowledging: forget the oldest rather than grow forever.
        for _ in range(len(unacked) - MAX_UNACKED):
            unacked.popitem(last=False)
    return len(packets)


# Reliable resends (UdpLibrary keeps every reliable packet until it is acknowledged): the
# client acknowledges with AckAll (00 15 | u16 seq: everything up to seq) or Ack (00 11 | u16
# seq: that one). An unacknowledged packet goes again after the connection's resend timeout
# (from its measured round trip, as TCP: smoothed RTT + 4 x variation, 0.3 to 5 s), doubling
# each time. Resends are rationed (per connection and per tick for the whole server): a
# server that falls behind reads acknowledgements late, and resending everything then only
# made it fall further behind (a resend storm in the 150-player load test).
RESEND_SECONDS = 1.0             # until the first round trip is measured
# At least 1 s: a busy server reads acknowledgements late (a burst of logins), and a shorter
# timeout resent packets that had arrived, which made it busier still.
MIN_RTO, MAX_RTO = 1.0, 6.0
FAST_RESEND_SECONDS = 0.1
MAX_RESEND_BACKOFF = 4
MAX_RESENDS = 12
MAX_RESENDS_PER_TICK = 8         # per connection
MAX_RESENDS_PER_TICK_ALL = 400   # for the whole server
RESEND_WINDOW = 16               # only the oldest packets of a connection are looked at
MAX_UNACKED = 4096
SEND_FAILURES = [0]              # sendto refused (send buffer full); logged by world_tick
RECEIVE_GAPS = [0]               # client packets that arrived after a missing one (lost on the way)


def full_seq(state, seq16):
    """The full sequence number of a u16 seq from the client (the last sent one at or before it)."""
    last = state["out_seq"] - 1
    return last - ((last - seq16) & 0xFFFF)


def handle_acks(state, data):
    """Forget the packets the client acknowledged in this datagram."""
    unacked = state.get("unacked")
    if not unacked:
        return
    for kind, seq16 in ack_packets(data):
        top = full_seq(state, seq16)
        if kind == 0x15:
            now = time.time()
            while unacked:
                first = next(iter(unacked))
                if first > top:
                    break
                _, entry = unacked.popitem(last=False)
                if entry[2] == 0:
                    rtt_sample(state, now - entry[3])
        else:
            # Ack1: this packet arrived ahead of a gap. Fast resend: the earlier unacknowledged
            # packets are very likely lost, so send them now (once per FAST_RESEND_SECONDS).
            unacked.pop(top, None)
            now = time.time()
            for seq, entry in list(unacked.items()):
                if seq >= top:
                    break
                if now - entry[1] >= FAST_RESEND_SECONDS:
                    try:
                        state["sock"].sendto(entry[0], state["addr"])
                    except (BlockingIOError, ConnectionResetError, KeyError):
                        break
                    entry[1] = now
                    state["resent"] = state.get("resent", 0) + 1


def rtt_sample(state, sample):
    """Update the connection's smoothed round trip and resend timeout (RFC 6298)."""
    srtt = state.get("srtt")
    if srtt is None:
        state["srtt"], state["rttvar"] = sample, sample / 2
    else:
        state["rttvar"] = 0.75 * state["rttvar"] + 0.25 * abs(srtt - sample)
        state["srtt"] = 0.875 * srtt + 0.125 * sample
    state["rto"] = max(MIN_RTO, min(MAX_RTO, state["srtt"] + 4 * state["rttvar"]))


def ack_packets(data):
    """(0x15 or 0x11, u16 seq) for every AckAll1 / Ack1 in a datagram, also inside Multi."""
    if len(data) < 4 or data[0] != 0:
        return
    if data[1] in (0x11, 0x15):
        yield data[1], struct.unpack_from(">H", data, 2)[0]
    elif data[1] == 0x03:
        pos = 2
        while pos < len(data):
            n = data[pos]
            yield from ack_packets(data[pos + 1:pos + 1 + n])
            pos += 1 + n


def resend_tick(clients, now):
    """Send again the oldest reliable packets that are overdue for an acknowledgement."""
    import itertools
    budget = MAX_RESENDS_PER_TICK_ALL
    for state in list(clients.values()):
        unacked = state.get("unacked")
        if not unacked or "sock" not in state or budget <= 0:
            continue
        rto = state.get("rto", RESEND_SECONDS)
        sent, drop = 0, []
        for seq, entry in itertools.islice(unacked.items(), RESEND_WINDOW):
            pkt, last, tries = entry[0], entry[1], entry[2]
            if now - last < rto * (2 ** min(tries, MAX_RESEND_BACKOFF)):
                continue
            if tries >= MAX_RESENDS:
                drop.append(seq)
                continue
            try:
                state["sock"].sendto(pkt, state["addr"])
            except (BlockingIOError, ConnectionResetError):
                break
            entry[1], entry[2] = now, tries + 1
            state["resent"] = state.get("resent", 0) + 1
            sent += 1
            if sent >= MAX_RESENDS_PER_TICK:
                break
        for seq in drop:
            unacked.pop(seq, None)
        budget -= sent
