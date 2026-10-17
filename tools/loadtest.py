"""Load test: many headless players log in and walk around, to see how the server copes.

Each bot speaks the client's protocol (SOE reliable UDP, then UE2 packets on the zone server):
it logs in with a launcher token, picks its character on the world server, joins the zone
(HELLO / LOGIN / JOIN) and then sends ShortServerMove a few times a second while walking in a
circle, plus a ping every second. The ping round trip (the server echoes type 9 at once) shows how
far behind the server's single loop is running.

    python tools/loadtest.py --setup 20          # make account "loadtest" and 20 bot characters
    python tools/loadtest.py --bots 20 --seconds 60
    python tools/loadtest.py --cleanup           # remove the bot characters and the account

Run it on the server machine (it reads the client's packages, like the server, to encode moves).
Start the server with --quiet-packets so its logging doesn't dominate. Uses the server's own
modules and the standard library only.
"""
import argparse
import json
import math
import os
import random
import secrets
import socket
import statistics
import struct
import sys
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import accounts      # noqa: E402
import rpc           # noqa: E402
import storage       # noqa: E402
import ue2net        # noqa: E402

ACCOUNT = "loadtest"
BOT_PREFIX = "Lbot"
CHARACTERS_FILE = MAIN_CHARACTERS_FILE = os.path.join(ROOT, "server", "characters.json")
PC_CHANNEL = 1
ACK_INTERVAL = 0.1          # seconds between a bot's acknowledgements
GAPS = [0]                  # server packets that arrived after a missing one
DROP = 0.0                  # share of incoming reliable packets ignored (--drop)
CAMP = (-31000.0, -5500.0, 460.0)
CHUNK = None                     # --at: another chunk [x, y] for the bots (default: where the template is)


def bot_name(i):
    """Letters only (the server's name rule): Lbotaa, Lbotab, ..."""
    a, b = divmod(i, 26)
    return BOT_PREFIX + chr(97 + a % 26) + chr(97 + b)


# --- setup ---------------------------------------------------------------------------------

def bot_account(i):
    """Each bot has its own account (as real players do: a login lists only that account's
    characters). Password login is disabled for them (an empty hash never matches); they log in
    with their launcher token."""
    return "lbot_" + bot_name(i)[len(BOT_PREFIX):]


def bot_token(i=0):
    return f"LB{i:06d}"


def is_bot_account(name):
    return name.startswith("lbot_") or name == ACCOUNT


BOT_MAX_ITEMS = 30                # bag items copied to each bot (the bags hold 50)


def setup(n, template_name):
    chars = storage.read_characters(CHARACTERS_FILE)
    template = next((c for c in chars + storage.read_characters(MAIN_CHARACTERS_FILE)
                     if c["first"] == template_name), None)
    if template is None:
        sys.exit(f"No character named {template_name} to copy.")
    data = accounts.load()
    now = int(time.time())
    for i in range(n):
        acc = bot_account(i)
        data["accounts"][acc] = {"name": acc, "salt": "", "hash": "", "iterations": 1, "created": now}
        data["launcher_tokens"][bot_token(i)] = acc
    accounts.save(data)
    keep = [c for c in chars if not is_bot_account(c.get("account") or "")]
    for i in range(n):
        c = {k: v for k, v in template.items() if k not in ("id", "guild", "brotherhood", "bound", "house")}
        # Room in the bags whatever the template carries (trades and loot need free slots).
        c["items"] = list(template.get("items", []))[:BOT_MAX_ITEMS]
        ang = 2 * 3.14159 * i / max(n, 1)
        c.update(first=bot_name(i), last="", account=bot_account(i),
                 position=[CAMP[0] + 300 * math.cos(ang), CAMP[1] + 300 * math.sin(ang), CAMP[2]])
        if CHUNK:
            c.update(chunk=list(CHUNK), position_chunk=list(CHUNK))
        keep.append(c)
    storage.write_characters(CHARACTERS_FILE, keep)
    print(f"{n} bot accounts (lbot_...) with one character each; launcher tokens {bot_token(0)}...")


def cleanup():
    chars = storage.read_characters(CHARACTERS_FILE)
    keep = [c for c in chars if not is_bot_account(c.get("account") or "")]
    storage.write_characters(CHARACTERS_FILE, keep)
    data = accounts.load()
    data["accounts"] = {k: v for k, v in data["accounts"].items() if not is_bot_account(k)}
    data["launcher_tokens"] = {t: u for t, u in data["launcher_tokens"].items() if not is_bot_account(u)}
    accounts.save(data)
    print(f"Removed {len(chars) - len(keep)} bot characters and their accounts.")


# --- SOE reliable UDP ----------------------------------------------------------------------

class SoeConnection:
    """Client side of one SOE connection: connect, reliable sends, acks, fragment reassembly."""

    def __init__(self, host, port, timeout=10.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # A big receive buffer: dozens of bots share one Python process and read in turns, and
        # Windows' default (64 KB) overflowed between reads (lost packets, resends, delays).
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self.sock.settimeout(timeout)
        self.addr = (host, port)
        self.out_seq = 0
        self.frag = None          # [total, bytes]
        self.inbox = []
        self.terminated = False   # the server sent Terminate (e.g. the character logged in elsewhere)
        self.expect = 0           # next reliable sequence number to deliver
        self.acked = None         # the server's last AckAll
        self.pending = {}         # seq -> packet that arrived early
        self.unacked = {}         # our seq -> [packet, last sent] until the server acknowledges it
        self.need_ack = False     # delivered something since our last AckAll
        self.last_ack = 0.0
        self.code = random.getrandbits(32)
        self.sock.sendto(struct.pack(">HIII", 1, 3, self.code, 512) + b"API_PROTOCOL_1.0\0", self.addr)
        self._recv_one()          # the confirm

    def send(self, payload):
        pkt = struct.pack(">BBH", 0, 0x09, self.out_seq & 0xFFFF) + payload
        self.unacked[self.out_seq] = [pkt, time.time()]
        self.sock.sendto(pkt, self.addr)
        self.out_seq += 1

    def maintain(self):
        """What UdpLibrary does between reads: one cumulative AckAll for everything delivered
        (not one per packet), and resends of our packets the server hasn't acknowledged."""
        now = time.time()
        if self.need_ack and now - self.last_ack >= ACK_INTERVAL:
            # Acknowledgements are batched (at most every ACK_INTERVAL), as a real client does;
            # one per read made the bots send far more packets than real players.
            self.sock.sendto(struct.pack(">BBH", 0, 0x15, (self.expect - 1) & 0xFFFF), self.addr)
            self.need_ack = False
            self.last_ack = now
        for seq, entry in list(self.unacked.items())[:16]:
            if now - entry[1] > 1.0:
                self.sock.sendto(entry[0], self.addr)
                entry[1] = now

    def close(self):
        try:
            self.sock.sendto(struct.pack(">HIH", 5, self.code, 6), self.addr)
        finally:
            self.sock.close()

    def _recv_one(self):
        data, _ = self.sock.recvfrom(65535)
        if len(data) < 2 or data[0] != 0:
            return
        kind = data[1]
        if kind == 0x05:
            self.terminated = True    # UdpLibrary Terminate: the server ended this connection
            return
        if kind == 0x15 and len(data) >= 4:
            self.acked = struct.unpack_from(">H", data, 2)[0]
            last = self.out_seq - 1
            top = last - ((last - self.acked) & 0xFFFF)
            for seq in [s for s in self.unacked if s <= top]:
                del self.unacked[seq]
            return
        if kind not in (0x09, 0x0D):
            return
        if DROP and random.random() < DROP:
            return                # simulated loss: no ack, so the server must send it again
        seq = struct.unpack_from(">H", data, 2)[0]
        ahead = (seq - self.expect) & 0xFFFF
        if ahead < 0x8000 and seq not in self.pending:
            self.pending[seq] = data
        if ahead and ahead < 0x8000:
            # Out of order (a packet before it is missing): Ack1 asks for a fast resend.
            self.sock.sendto(struct.pack(">BBH", 0, 0x11, seq), self.addr)
            GAPS[0] += 1
        # Deliver in order (UdpLibrary does), then acknowledge everything delivered so far.
        while self.expect in self.pending:
            self._deliver(self.pending.pop(self.expect))
            self.expect = (self.expect + 1) & 0xFFFF
        self.need_ack = True      # sent by maintain()

    def _deliver(self, data):
        if data[1] == 0x09:
            self.inbox.append(data[4:])
            return
        if self.frag is None:
            total = struct.unpack_from(">I", data, 4)[0]
            self.frag = [total, data[8:]]
        else:
            self.frag[1] += data[4:]
        if len(self.frag[1]) >= self.frag[0]:
            self.inbox.append(self.frag[1][:self.frag[0]])
            self.frag = None

    def messages(self, until=None, timeout=10.0):
        """Application messages as they arrive; stop when until(msg) is true (returns it)."""
        end = time.time() + timeout
        while time.time() < end:
            while self.inbox:
                m = self.inbox.pop(0)
                if until is None or until(m):
                    return m
            try:
                self._recv_one()
                self.maintain()
            except socket.timeout:
                self.maintain()
                break
        return None

    def poll(self):
        """Read whatever has arrived without waiting."""
        self.sock.settimeout(0)
        try:
            while True:
                self._recv_one()
        except (BlockingIOError, socket.timeout):
            pass
        except OSError:
            pass
        finally:
            self.sock.settimeout(10.0)
        self.maintain()
        out, self.inbox = self.inbox, []
        return out


def login_request(account, password):
    a, p = account.encode("latin-1"), password.encode("latin-1")
    return struct.pack("<HI", 3, len(a)) + a + struct.pack("<I", len(p)) + p


def event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def is_event(msg, event_id):
    return len(msg) >= 10 and struct.unpack_from("<HI", msg, 0) == (2, event_id)


def wfield(text, size=128):
    raw = text[:size // 2 - 1].encode("utf-16-le")
    return raw + b"\0" * (size - len(raw))


def wtext(raw):
    return raw.decode("utf-16-le", "replace").split("\0")[0]


# --- one bot -------------------------------------------------------------------------------

class Bot(threading.Thread):
    def __init__(self, i, args, token, net_cache, stats):
        super().__init__(daemon=True)
        self.i, self.args, self.token, self.nc, self.stats = i, args, token, net_cache, stats
        self.name = bot_name(i)
        self.joined_at = None
        self.error = None
        self.rtts = []
        self.rtt_times = []       # when each ping was sent (wall clock)
        self.joined_wall = None

    def run(self):
        try:
            self.play()
        except Exception as e:      # report and stop this bot only
            self.error = f"{type(e).__name__}: {e}"

    def play(self):
        a, start = self.args, time.time()
        # Login server: launcher token -> account and session key (event 0x27).
        c = SoeConnection(a.host, a.login_port)
        c.send(login_request("SOE_LOGIN", self.token))
        m = c.messages(lambda m: is_event(m, 0x27))
        c.close()
        if m is None:
            raise RuntimeError("no world-server event from the login server")
        account, session = wtext(m[10:138]), wtext(m[138:266])
        # World server: log in, list characters, play.
        w = SoeConnection(a.host, a.world_port)
        w.send(login_request(account, session))
        w.messages(lambda m: is_event(m, 1))
        w.send(event(0x19))
        w.send(event(0x19, wfield(self.name) + bytes.fromhex("0100ffff0100ffff00000000")))
        m = w.messages(lambda m: is_event(m, 8))
        if m is None:
            raise RuntimeError("no zone-connect event from the world server")
        zone_port = struct.unpack_from("<I", m, 10)[0]
        self.world = w            # kept: tells, shouts and other slash commands go through it
        # Zone server: log in, then the UE2 handshake.
        z = SoeConnection(a.host, zone_port)
        z.send(login_request(account, session))
        ue = {"pid": 0, "seq": 0}

        def unreal(bunches):
            pkt = ue2net.encode_packet(ue["pid"], (), bunches)
            ue["pid"] = (ue["pid"] + 1) % ue2net.MAX_PACKETID
            z.send(struct.pack("<HI", 1, len(pkt)) + pkt)

        def control(text, first=False):
            ue["seq"] += 1
            unreal([ue2net.Bunch(0, ue2net.fstring(text), reliable=True, control=True, open_=first,
                                 ch_type=ue2net.CHTYPE_CONTROL, seq=ue["seq"])])

        def control_text(msg):
            if len(msg) < 6 or struct.unpack_from("<H", msg, 0)[0] != 1:
                return []
            try:
                _, _, bunches = ue2net.decode_packet(msg[6:6 + struct.unpack_from("<I", msg, 2)[0]])
            except ValueError:
                return []
            return [t for b in bunches if b.channel == 0 and len(b.data) * 8 == b.nbits
                    for t in ue2net.read_fstrings(b.data)]

        control("HELLO REVISION=0 MINVER=3151 VER=3186", first=True)
        if z.messages(lambda m: any(t.startswith("CHALLENGE") for t in control_text(m))) is None:
            raise RuntimeError("no CHALLENGE")
        control("LOGIN")
        if z.messages(lambda m: any(t.startswith("WELCOME") for t in control_text(m))) is None:
            raise RuntimeError("no WELCOME")
        control("JOIN")
        self.joined_at = time.time() - start
        self.joined_wall = time.time()
        if not self.walk(z, unreal):            # True: the caller keeps the connection
            z.close()

    def walk(self, z, unreal):
        a = self.args
        f = self.nc.field("PlayerController", "ShortServerMove")
        spread = max(400.0, a.spread)
        cx, cy = CAMP[0] + random.uniform(-spread, spread), CAMP[1] + random.uniform(-spread, spread)
        r, t0 = random.uniform(100, 300), time.time()
        end = t0 + a.seconds
        next_move = next_ping = next_accept = t0
        pings = {}
        while time.time() < end:
            now = time.time()
            if now >= next_move:
                ang = (now - t0) * 0.5 + self.i
                loc = (int(cx + r * math.cos(ang)), int(cy + r * math.sin(ang)), int(CAMP[2]))
                data, nbits = rpc.encode_rpc(self.nc, "PlayerController", "ShortServerMove",
                                             {"TimeStamp": now - t0, "ClientLoc": loc, "View": 0})
                unreal([ue2net.Bunch(PC_CHANNEL, data, reliable=False, nbits=nbits)])
                next_move = now + 1.0 / a.move_rate if a.move_rate > 0 else end   # 0: stand still
            if a.auto_accept and now >= next_accept:
                # Accept any group / raid invite (0xb1); without a pending invite the server ignores it.
                z.send(event(0xB1))
                next_accept = now + 0.5
            if now >= next_ping:
                stamp = time.time_ns()     # the server logs how late pings arrive
                pings[stamp] = now
                z.send(struct.pack("<HQ", 9, stamp))
                next_ping = now + 1.0
            for m in z.poll():
                if a.auto_accept and len(m) >= 14 and struct.unpack_from("<HI", m, 0) == (2, 0x6C5):
                    # Ready check (0x6c5 {initiator row}): answer 0xa9 {row, 1 ready}.
                    z.send(event(0xA9, struct.pack("<ii", struct.unpack_from("<i", m, 10)[0], 1)))
                if len(m) == 10 and struct.unpack_from("<H", m, 0)[0] == 9:
                    sent = pings.pop(struct.unpack_from("<Q", m, 2)[0], None)
                    if sent is not None:
                        self.rtts.append((time.time() - sent) * 1000)
                        self.rtt_times.append(sent)
            time.sleep(0.01)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--setup", type=int, metavar="N", help="make the loadtest account and N characters")
    ap.add_argument("--template", default="Ranger", help="character copied for --setup")
    ap.add_argument("--cleanup", action="store_true", help="remove the bot characters and account")
    ap.add_argument("--bots", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--move-rate", type=float, default=4.0, help="moves per second per bot")
    ap.add_argument("--spread", type=float, default=400.0, help="bots walk within this many units of "
                    "the camp (400: a crowd; 40000: spread over the chunk)")
    ap.add_argument("--stagger", type=float, default=0.2, help="seconds between bot logins")
    ap.add_argument("--auto-accept", action="store_true", help="bots accept group and raid invites and answer ready checks")
    ap.add_argument("--drop", type=float, default=0.0, help="ignore this share of the server's "
                    "reliable packets (simulated loss: the server has to resend them)")
    ap.add_argument("--procs", type=int, default=1, help="bot processes (one Python process tops out "
                    "around 50 bots)")
    ap.add_argument("--first", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--data-dir", help="the server's --data-dir, if it uses one (for --setup / --cleanup)")
    ap.add_argument("--at", metavar="CX,CY,X,Y,Z",
                    help="put the bots (--setup) and their walk in another chunk, e.g. a crowded city: "
                         "--at=-13,-9,-3276,-45175,1545 (Khal; with = since it starts with -)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--login-port", type=int, default=10101)
    ap.add_argument("--world-port", type=int, default=10100)
    a = ap.parse_args(argv)
    if a.at:
        global CAMP, CHUNK
        cx, cy, x, y, z = (float(v) for v in a.at.split(","))
        CHUNK, CAMP = (int(cx), int(cy)), (x, y, z)
    if a.data_dir:
        global CHARACTERS_FILE
        os.makedirs(a.data_dir, exist_ok=True)
        CHARACTERS_FILE = os.path.join(os.path.abspath(a.data_dir), "characters.json")
        accounts.ACCOUNTS_FILE = os.path.join(os.path.abspath(a.data_dir), "accounts.json")
    if a.cleanup:
        cleanup()
        return 0
    if a.setup:
        setup(a.setup, a.template)
        return 0
    global DROP
    DROP = a.drop
    if a.procs > 1 and not a.child:
        return run_processes(a)
    import zone
    pm = zone.package_map(types.SimpleNamespace(client_dir=ROOT, package_maps={}), "chunk_n19_12")
    if bot_account(a.first) not in accounts.load()["accounts"]:
        sys.exit("Run --setup first.")
    bots = []
    for i in range(a.first, a.first + a.bots):
        b = Bot(i, a, bot_token(i), pm.net_cache, None)
        b.start()
        bots.append(b)
        time.sleep(a.stagger)
    for b in bots:
        b.join(a.seconds + 60)
    results = [{"name": b.name, "joined": b.joined_at, "joined_wall": b.joined_wall, "rtts": b.rtts,
                "rtt_times": b.rtt_times, "error": b.error} for b in bots]
    if a.child:
        results.append({"name": "_gaps", "joined": None, "rtts": [], "error": None, "gaps": GAPS[0]})
        print(json.dumps(results))
        return 0
    return report(results)


def run_processes(a):
    """Split the bots over a.procs child processes and merge their results."""
    import subprocess
    per, extra = divmod(a.bots, a.procs)
    procs, first = [], 0
    for k in range(a.procs):
        n = per + (1 if k < extra else 0)
        cmd = [sys.executable, os.path.abspath(__file__), "--child", "--bots", str(n), "--first", str(first),
               "--seconds", str(a.seconds), "--move-rate", str(a.move_rate), "--drop", str(a.drop),
               "--spread", str(a.spread)] + (["--auto-accept"] if a.auto_accept else []) + [
               "--stagger", str(a.stagger * a.procs), "--host", a.host,
               "--login-port", str(a.login_port), "--world-port", str(a.world_port)] + (
               ["--at", a.at] if a.at else []) + (
               ["--data-dir", a.data_dir] if a.data_dir else [])
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True))
        first += n
        time.sleep(a.stagger)
    results = []
    for p in procs:
        out, _ = p.communicate()
        results.extend(json.loads(out.strip().splitlines()[-1]) if out.strip() else [])
    return report(results, a.bots)


def report(results, expected=None):
    gaps = sum(r.get("gaps", 0) for r in results if r["name"] == "_gaps") + GAPS[0]
    results = [r for r in results if r["name"] != "_gaps"]
    expected = expected or len(results)
    print(f"server packets that arrived after a lost one (seen by the bots): {gaps}")
    joined = [r for r in results if r["joined"] is not None]
    rtts = sorted(x for r in results for x in r["rtts"])
    print(f"{len(joined)}/{expected} bots joined the zone", end="")
    if joined:
        print(f" (login to JOIN: median {statistics.median(r['joined'] for r in joined):.2f}s, "
              f"max {max(r['joined'] for r in joined):.2f}s)")
    else:
        print()
    if rtts:
        p = lambda q: rtts[min(len(rtts) - 1, int(q * len(rtts)))]
        print(f"ping round trip over {len(rtts)} pings: median {p(0.5):.1f} ms, p95 {p(0.95):.1f} ms, "
              f"max {rtts[-1]:.1f} ms")
    if joined:
        settled = max(r["joined_wall"] for r in joined) + 5
        steady = sorted(x for r in results for x, t in zip(r["rtts"], r.get("rtt_times", ())) if t >= settled)
        if steady:
            q = lambda f: steady[min(len(steady) - 1, int(f * len(steady)))]
            print(f"  steady state (from 5 s after the last join, {len(steady)} pings): median {q(0.5):.1f} ms, "
                  f"p95 {q(0.95):.1f} ms, max {steady[-1]:.1f} ms")
    for r in results:
        if r["error"]:
            print(f"  {r['name']}: {r['error']}")
    return 0 if len(joined) == expected else 1

if __name__ == "__main__":
    sys.exit(main())
