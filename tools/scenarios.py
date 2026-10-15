"""Multiplayer scenarios with two headless players: things that otherwise need two people.

Two load-test bots (Lbotaa = A, Lbotab = B) log in to a running server and go through:
  chat   A says something, B receives the chat line
  group  A invites B, B accepts
  trade  A offers an item, B offers 50 copper, both accept; the database must show the item
         with B and the coins with A
  tell   A sends B a private message
  friend A adds B to the friends list (and removes B again)
  brotherhood  A invites B, B joins (checked in the database) and leaves again
  guild  A founds a guild and invites B, B joins (checked in the database), A disbands it
  duel   A challenges B, B accepts, the countdown runs and the duel starts
  aa     A trains an alternate advancement ability (0x85a); the server answers 0x860 and
         saves the rank and the spent point
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
        storage.update_character(CHARACTERS, loadtest.bot_name(0),
                                 {"aa_points": 3, "aa_spent": 0, "aa_ranks": {}})
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
    # Tell: world message type 6 {u32 0x14, u32 length, wstr 'tell "Name" text'}; B gets it on
    # its own world or zone connection.
    text = 'tell "%s" psst from A' % b.name
    a.world.send(struct.pack("<HII", 6, 0x14, len(wstr(text))) + wstr(text))
    end = time.time() + 3
    heard = False
    while time.time() < end and not heard:
        b.pump(0.2)
        heard = any("psst from A".encode("utf-16-le") in m for m in b.got + b.world.poll())
    fails += check("tell", heard)

    # Friends: world social message (type 5) 0x4f7 {wstr name, bool8 add}; A gets 0x4f2 (added).
    a.world.send(struct.pack("<HII", 5, 0x4F7, len(wstr(b.name)) + 1) + wstr(b.name) + bytes([1]))
    end, added = time.time() + 3, False
    while time.time() < end and not added:
        a.pump(0.2)
        added = any(len(m) >= 6 and struct.unpack_from("<I", m, 2)[0] == 0x4F2 for m in a.got + a.world.poll())
    fails += check("friend", added)
    a.world.send(struct.pack("<HII", 5, 0x4F7, len(wstr(b.name)) + 1) + wstr(b.name) + bytes([0]))

    # Guild: A founds one (0x4d3 {eid64, wstr name}), invites B (0x4d5 {wstr}), B gets the
    # popup (0x4e9) and accepts (0x4d6); the saved guild lists both. Then A disbands it (0x4da).
    gname = "Scenario Guild %d" % (int(time.time()) % 100000)
    a.send(0x4D3, bytes(8) + wstr(gname))
    a.pump(0.5)
    a.send(0x4D5, wstr(b.name))
    invited = b.wait_for(0x4E9)
    b.send(0x4D6)
    b.pump(0.5)
    guilds = storage.read_json(os.path.join(ROOT, "server", "guilds.json"), {})
    g = next((g for g in guilds.values() if g.get("name") == gname), None)
    members = sorted(g["members"]) if g else []
    fails += check("guild", bool(invited) and members == sorted([a.name, b.name]),
                   f"invite popup={bool(invited)}, members={members}")
    a.send(0x4DA)
    a.pump(0.5)

    # Brotherhood: A invites B (0x4bd {wstr}), B gets the popup (0x4bd) and accepts (0x4be);
    # the saved brotherhood lists both. B leaves (0x4c0): one member left, so it is dropped.
    path = os.path.join(ROOT, "server", "brotherhoods.json")
    a.send(0x4BD, wstr(b.name))
    popup = b.wait_for(0x4BD)
    b.send(0x4BE)
    b.pump(0.5)
    bh = next((x for x in storage.read_json(path, []) if a.name in x.get("members", [])), None)
    joined = bool(bh) and sorted(bh["members"]) == sorted([a.name, b.name])
    b.send(0x4C0)
    b.pump(0.5)
    gone = not any(a.name in x.get("members", []) for x in storage.read_json(path, []))
    fails += check("brotherhood", bool(popup) and joined and gone,
                   f"popup={bool(popup)}, both saved={joined}, dropped after leaving={gone}")

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
    # Alternate advancement: A trains Hardiness (1001, 1 point) with 0x85a {i32 id}; the server
    # answers 0x860 {id, list, rank, cost} and saves the rank and the points.
    a.send(0x85A, struct.pack("<i", 1001))
    trained = a.wait_for(0x860)
    time.sleep(0.3)
    saved = storage.read_character(CHARACTERS, a.name)
    ok = (bool(trained) and struct.unpack_from("<iiii", trained[0])[:3] == (1001, 0, 1)
          and saved.get("aa_ranks", {}).get("1001") == 1 and saved.get("aa_spent") == 1)
    fails += check("aa", ok, f"0x860={bool(trained)}, ranks={saved.get('aa_ranks')}, spent={saved.get('aa_spent')}")
    a.zone.close()
    b.zone.close()
    print(f"{fails} failed")
    return fails


if __name__ == "__main__":
    sys.exit(main())
