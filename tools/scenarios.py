"""Multiplayer scenarios with two headless players: things that otherwise need two people.

Two load-test bots (Lbotaa = A, Lbotab = B) log in to a running server and go through:
  chat   A says something, B receives the chat line
  group  A invites B, B accepts
  trade  A offers an item, B offers 50 copper, both accept; the database must show the item
         with B and the coins with A
  duel   A challenges B, B accepts, the countdown runs and the duel starts
Each step prints PASS or FAIL; the exit code is the number of failures.

    python tools/scenarios.py --setup                 (makes the two bots, gives B coins)
    python server/login_stub.py --quiet-packets      (in another window)
    python tools/scenarios.py
    python tools/loadtest.py --cleanup                (removes the bots again)

Uses the server's own modules and the standard library only.
"""
import os
import struct
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "server"))

import loadtest      # noqa: E402
import storage       # noqa: E402

CHARACTERS = os.path.join(ROOT, "server", "characters.json")


class Player(loadtest.Bot):
    """A bot that keeps its zone connection and collects what the server sends."""

    def walk(self, z, unreal):
        self.zone, self.got = z, []
        return True

    def send(self, event_id, data=b""):
        self.zone.send(loadtest.event(event_id, data))

    def pump(self, seconds=0.5):
        end = time.time() + seconds
        while time.time() < end:
            self.got.extend(self.zone.poll())
            time.sleep(0.02)

    def events(self, event_id):
        return [m[10:] for m in self.got if len(m) >= 10 and struct.unpack_from("<HI", m, 0) == (2, event_id)]

    def wait_for(self, event_id, seconds=5.0):
        end = time.time() + seconds
        while time.time() < end:
            found = self.events(event_id)
            if found:
                return found
            self.pump(0.1)
        return []


def wstr(text):
    return (text + "\0").encode("utf-16-le")


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(': ' + detail) if detail else ''}")
    return 0 if ok else 1


def trade_seq(p):
    """The newest trade sequence number this player has seen."""
    seqs = [0]
    for event_id, off in ((0x1FC, 0), (0x1FE, 0), (0x1FF, 0), (0x20A, 8), (0x20B, 8), (0x202, 0),
                          (0x203, 0), (0x204, 0)):
        for data in p.events(event_id):
            if len(data) >= off + 4:
                seqs.append(struct.unpack_from("<i", data, off)[0])
    return max(seqs)


def main():
    if sys.argv[1:] == ["--setup"]:
        loadtest.setup(2, "Ranger")
        storage.update_character(CHARACTERS, loadtest.bot_name(1), {"coins": 500})
        return 0
    import zone
    pm = zone.package_map(types.SimpleNamespace(client_dir=ROOT, package_maps={}), "chunk_n19_12")
    args = types.SimpleNamespace(host="127.0.0.1", login_port=10101, world_port=10100, seconds=0, move_rate=1)
    a = Player(0, args, loadtest.bot_token(0), pm.net_cache, None)
    b = Player(1, args, loadtest.bot_token(1), pm.net_cache, None)
    a.play()
    b.play()
    a.pump(1.0)
    b.pump(1.0)
    fails = 0

    # Chat: zone say (0x74); others get zone event 0x0f with the text.
    a.send(0x74, wstr("hello from A"))
    b.pump(1.0)
    fails += check("chat", any(wstr("hello from A")[:-2] in d for d in b.events(0x0F)))

    # Group: invite (0xb0 {wstr name}), accept (0xb1).
    a.send(0xB0, wstr(b.name))
    b.pump(0.5)
    b.send(0xB1)
    a.pump(1.0)
    b.pump(0.5)
    fails += check("group", len(a.got) > 0 and any(len(m) >= 10 and 0x6B0 <= struct.unpack_from("<I", m, 2)[0] <= 0x6DF
                                                      for m in b.got if m[:2] == b"\x02\x00"),
                   "B received group window messages")

    # Trade: A's first bag item for 50 of B's copper.
    before_a = storage.read_character(CHARACTERS, a.name)
    before_b = storage.read_character(CHARACTERS, b.name)
    item = next((i for i in before_a.get("items", []) if i[4] < 1000000), None)
    if item is None or before_b.get("coins", 0) < 50:
        return fails + check("trade", False, "A has no bag item or B has under 50 copper")
    a.send(0xC0, wstr(b.name))
    if not b.wait_for(0x208):
        return fails + check("trade", False, "B got no invite")
    b.send(0xC3)
    a.pump(0.5)
    a.send(0xC4, struct.pack("<iii", item[0], 0, item[3]))
    a.pump(0.5)
    b.pump(0.5)
    b.send(0xC6, struct.pack("<qi", 50, trade_seq(b)))
    a.pump(0.5)
    b.pump(0.5)
    seq = max(trade_seq(a), trade_seq(b))
    a.send(0xC7, struct.pack("<i", seq))
    b.send(0xC7, struct.pack("<i", seq))
    done = a.wait_for(0x201) and b.wait_for(0x201)
    time.sleep(0.5)
    after_a = storage.read_character(CHARACTERS, a.name)
    after_b = storage.read_character(CHARACTERS, b.name)
    moved = (sum(1 for i in after_b["items"] if i[1] == item[1]) == sum(1 for i in before_b.get("items", []) if i[1] == item[1]) + 1
             and not any(i[0] == item[0] for i in after_a["items"]))
    coins = after_a.get("coins", 0) - before_a.get("coins", 0) == 50 and before_b.get("coins", 0) - after_b.get("coins", 0) == 50
    fails += check("trade", bool(done) and moved and coins,
                   f"done={bool(done)}, {item[1]} moved={moved}, 50 copper moved={coins}")
    # Duel: A picks B as defensive target (0x5c {u64}), challenges (0x3fd); B accepts
    # (0x3ff {0}); both get the countdown (0x400), then the start (0x401) after 10 s.
    import login_stub
    b_id = login_stub.character_id(dict(storage.read_character(CHARACTERS, b.name)))
    if b_id is None:
        fails += check("duel", False, "B has no character id yet")
    else:
        a.send(0x5C, struct.pack("<Q", b_id))
        a.send(0x3FD)
        challenged = b.wait_for(0x3FE)
        b.send(0x3FF, struct.pack("<i", 0))
        countdown = a.wait_for(0x400) and b.wait_for(0x400)
        started = a.wait_for(0x401, 15) and b.wait_for(0x401, 15)
        fails += check("duel", bool(challenged and countdown and started),
                       f"challenge={bool(challenged)}, countdown={bool(countdown)}, start={bool(started)}")
    a.zone.close()
    b.zone.close()
    print(f"{fails} failed")
    return fails


if __name__ == "__main__":
    sys.exit(main())
