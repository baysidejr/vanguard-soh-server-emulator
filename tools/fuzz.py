"""Fuzz the zone server: random payloads for every client event id, from a logged-in bot.

A server must survive anything a client sends. This logs one load-test bot into the zone, then
sends every event id from 1 to --max-event with random payloads of awkward sizes, checking with
a ping after each id that the server still answers. A silent server is retried with a fresh
login: if that works the event only closed the bot's connection (camping, chunk travel), if not
the server hung. Afterwards it lists the handler errors from the server log by event id.

Run it against a server with its own data folder, since random events change saved data:

    python tools/loadtest.py --data-dir C:/vgfuzz --setup 1
    python server/login_stub.py --quiet-packets --dev-commands --data-dir C:/vgfuzz > fuzz_log.txt
    python tools/fuzz.py --log fuzz_log.txt

Uses the server's own modules and the standard library only.
"""
import argparse
import os
import random
import re
import struct
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "server"))

import loadtest      # noqa: E402

SIZES = (0, 1, 2, 3, 4, 7, 8, 12, 16, 33, 64, 200, 600)


class FuzzBot(loadtest.Bot):
    """A bot that stops after JOIN and keeps its zone connection for fuzzing."""

    def walk(self, z, unreal):
        self.zone = z
        self.unreal = unreal
        return True


def login(args, token, net_cache):
    bot = FuzzBot(0, args, token, net_cache, None)
    bot.play()
    return bot


def alive(z, timeout=3.0):
    stamp = random.getrandbits(63)
    z.send(struct.pack("<HQ", 9, stamp))
    end = time.time() + timeout
    while time.time() < end:
        for m in z.poll():
            if len(m) == 10 and struct.unpack_from("<HQ", m, 0) == (9, stamp):
                return True
        time.sleep(0.01)
    return False


# Passes: chat commands (the server needs --dev-commands) that put the bot in a situation first,
# so handlers that need a target, a window or a session get past their first check.
CONTEXTS = [
    [],
    ["!tp -30650 -5650 560 32768", "!target Camp Forge", ("event", 0xFA)],
    ["!target Orin the Trader", "!give Copper Ore 5", "!give Hunter's Shortsword"],
    ["!target Hollis Grent"],
    ["!target Garret Holm"],
    ["!tp -33000 -3900 g 0", "!target Canyon Widow"],
    ["!target Mailbox", "!give Small Pouch"],
]


def say(z, text):
    z.send(loadtest.event(0x74, (text + "\0").encode("utf-16-le")))


def enter(bot, context):
    for step in context:
        if isinstance(step, tuple):
            bot.zone.send(loadtest.event(step[1]))
        else:
            say(bot.zone, step)
        time.sleep(0.2)


def acked(conn, timeout=3.0):
    """Send a message no handler knows and wait for the server to acknowledge it."""
    conn.send(struct.pack("<H", 0x7777))
    want = (conn.out_seq - 1) & 0xFFFF
    end = time.time() + timeout
    while time.time() < end:
        conn.poll()
        if conn.acked == want:
            return True
        time.sleep(0.01)
    return False


def world_login(a, token):
    """A logged-in world connection (as the client has before Play)."""
    c = loadtest.SoeConnection(a.host, a.login_port)
    c.send(loadtest.login_request("SOE_LOGIN", token))
    m = c.messages(lambda m: loadtest.is_event(m, 0x27))
    c.close()
    account, session = loadtest.wtext(m[10:138]), loadtest.wtext(m[138:266])
    w = loadtest.SoeConnection(a.host, a.world_port)
    w.send(loadtest.login_request(account, session))
    w.messages(lambda m: loadtest.is_event(m, 1))
    return w


def login_conn(a, token):
    c = loadtest.SoeConnection(a.host, a.login_port)
    c.send(loadtest.login_request("SOE_LOGIN", token))
    c.messages(lambda m: loadtest.is_event(m, 0x27))
    return c


def world_fuzz(a, lt, token, rng):
    """Every login-connection event id (character create / delete live there), then every world
    event id (message type 2), plus social (5) and command (6) messages."""
    c = login_conn(lt, token)
    for ev in range(1, a.max_event + 1):
        for data in payloads(rng, a.per_event):
            c.send(loadtest.event(ev, data))
        if not acked(c):
            try:
                c = login_conn(lt, token)
            except Exception as e:
                print(f"Login server: STOPPED ANSWERING after {ev:#x}: {type(e).__name__}: {e}")
                return (ev, str(e))
    c.close()
    print(f"Login server: event ids 1-{a.max_event:#x} sent")
    w = world_login(lt, token)
    hung = None
    for ev in range(1, a.max_event + 1):
        if ev == 0x19:
            continue                       # Play: hands the bot to the zone
        for data in payloads(rng, a.per_event):
            w.send(loadtest.event(ev, data))
        for data in payloads(rng, 2):
            w.send(struct.pack("<HII", 5, ev, len(data)) + data)
        if ev < 0x40:
            for data in payloads(rng, 4):
                w.send(struct.pack("<HII", 6, 0x14, len(data)) + data)
        if acked(w):
            continue
        try:
            w = world_login(lt, token)
        except Exception as e:
            hung = (ev, f"{type(e).__name__}: {e}")
            break
    print(f"World server: event ids 1-{a.max_event:#x} sent" + (f"; STOPPED ANSWERING after {hung[0]:#x}: {hung[1]}" if hung else ""))
    return hung


def payloads(rng, n):
    for _ in range(n):
        size = rng.choice(SIZES)
        kind = rng.random()
        if kind < 0.3:
            yield bytes(size)
        elif kind < 0.5:
            yield b"\xff" * size
        elif kind < 0.7:                       # small ints, the common field type
            yield b"".join(struct.pack("<i", rng.choice((0, 1, -1, 2, 1000, 0x7FFFFFFF, -0x80000000)))
                           for _ in range(max(1, size // 4)))
        else:
            yield bytes(rng.getrandbits(8) for _ in range(size))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max-event", type=lambda v: int(v, 0), default=0x900)
    ap.add_argument("--first-event", type=lambda v: int(v, 0), default=1)
    ap.add_argument("--per-event", type=int, default=12, help="random payloads per event id")
    ap.add_argument("--skip", default="", help="comma-separated event ids not to send")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--contexts", action="store_true", help="repeat the sweep after each setup in "
                    "CONTEXTS (target a station, merchant, banker, mob...); the server needs --dev-commands")
    ap.add_argument("--world", action="store_true", help="sweep the world server's messages first")
    ap.add_argument("--raw", type=int, default=50, help="rounds of random UE2 packets / message types / datagrams")
    ap.add_argument("--log", help="the server's log, to list handler errors afterwards")
    ap.add_argument("--data-dir", help="the server's --data-dir (to find the bot's token)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--login-port", type=int, default=10101)
    ap.add_argument("--world-port", type=int, default=10100)
    a = ap.parse_args(argv)
    lt = types.SimpleNamespace(host=a.host, login_port=a.login_port, world_port=a.world_port,
                               seconds=0, move_rate=1)
    if a.data_dir:
        loadtest.accounts.ACCOUNTS_FILE = os.path.join(os.path.abspath(a.data_dir), "accounts.json")
    import zone
    pm = zone.package_map(types.SimpleNamespace(client_dir=ROOT, package_maps={}), "chunk_n19_12")
    token = loadtest.bot_token()
    rng = random.Random(a.seed)
    skip = {int(x, 0) for x in a.skip.split(",") if x}
    rng_world = random.Random(a.seed + 1)
    if a.world and world_fuzz(a, lt, token, rng_world):
        return 1
    bot = login(lt, token, pm.net_cache)
    closed, hung = [], None
    start = time.time()
    contexts = CONTEXTS if a.contexts else CONTEXTS[:1]
    ev = a.first_event
    for ci, context in enumerate(contexts):
        enter(bot, context)
        for ev in range(a.first_event, a.max_event + 1):
            if ev in skip:
                continue
            for data in payloads(rng, a.per_event):
                bot.zone.send(loadtest.event(ev, data))
            if alive(bot.zone):
                continue
            try:
                bot = login(lt, token, pm.net_cache)
            except Exception as e:
                hung = (ev, f"{type(e).__name__}: {e}")
                break
            closed.append(ev)
            enter(bot, context)
        if hung:
            break
        if len(contexts) > 1:
            print(f"  pass {ci + 1}/{len(contexts)} done ({' / '.join(str(x) for x in context) or 'no setup'})")
    print(f"Sent event ids {a.first_event:#x}-{ev:#x}, {a.per_event} payloads each, in {time.time() - start:.0f} s.")
    if not hung and a.raw:
        # Other zone message types (1 = a UE2 packet, 9 = ping, unknown types), then datagrams
        # that skip the reliable layer altogether.
        for round_ in range(a.raw):
            for data in payloads(rng, 20):
                bot.zone.send(struct.pack("<HI", 1, len(data)) + data)
                bot.zone.send(struct.pack("<H", rng.randrange(0, 40)) + data)
                bot.zone.sock.sendto(bytes([0, rng.randrange(0, 40)]) + data, bot.zone.addr)
            if not alive(bot.zone):
                try:
                    bot = login(lt, token, pm.net_cache)
                    closed.append(f"raw round {round_}")
                except Exception as e:
                    hung = (-1, f"raw round {round_}: {type(e).__name__}: {e}")
                    break
        print(f"Sent {a.raw} rounds of random UE2 packets, message types and raw datagrams.")
    if closed:
        print("Connection closed after (re-logged in): " + ", ".join(f"{e:#x}" if isinstance(e, int) else e for e in closed))
    if hung:
        print(f"SERVER STOPPED ANSWERING after event {hung[0]:#x}: {hung[1]}" if hung[0] >= 0 else f"SERVER STOPPED ANSWERING: {hung[1]}")
    if a.log and os.path.exists(a.log):
        text = open(a.log, encoding="utf-8", errors="replace").read()
        errors = re.findall(r"handler error for ([0-9a-f ]+)\n(?:.*\n)*?(\w+Error: [^\n]*)", text)
        by_event = {}
        for head, err in errors:
            b = bytes.fromhex(head.replace(" ", ""))
            key = struct.unpack_from("<I", b, 2)[0] if len(b) >= 6 and b[0] == 2 else -1
            by_event.setdefault(key, set()).add(err.strip())
        crashes = len(re.findall(r"!!! error in", text))
        print(f"Handler errors in {len(by_event)} event ids ({len(errors)} in all); {crashes} errors outside handlers.")
        for key in sorted(by_event):
            print(f"  {key:#x}: " + " | ".join(sorted(by_event[key]))[:200])
    return 1 if hung else 0


if __name__ == "__main__":
    sys.exit(main())
