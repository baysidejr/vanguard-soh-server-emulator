"""Diplomacy parleys (docs/DIPLOMACY.md; client handler FUN_00556560).

At parley start: 0x331 {i32 slots}, 0x21c, 0x21f {i32 n, n x card}, 0x237 {i32 card, i32 slot}.
NPC dialogue option type 10 -> client 0x125 {i32 id}
  -> 0x31d open {eid64 npc, u8 status (bar, 11 = middle), u8 dp, u8 opp dp,
     u8 x8 expression pools, u8 parley type, wstr}
client 0xd9 {i32 card} select -> 0x332 {i32 card}
client 0xda play -> 0x32c {u8 status, u8 x8}, 0x337 {i32 dp, i32 opp}, 0x333,
   0x218 NPC card, 0x325 {wstr NPC line}, 0x256 new round, 0x334 your turn
win 0x324, loss 0x31f {bool8}, XP 0x3d5 kind 2, close 0x338; client 0x12a
cancel, 0x12b close, 0x12c pass; errors 0x330 {i32 code, i32 arg}.

Cards and parleys are data (content/diplomacy.json). A card pushes the bar
toward its player by "push" (the NPC's cards push it back), costs expression
points ("cost") and gains some ("gain"). Expressions: reason, inspire,
flatter, demand."""
import random
import struct

START, SELECT, PLAY, PASS, CANCEL, CLOSE = 0x125, 0xD9, 0xDA, 0x12C, 0x12A, 0x12B
SLOT, UNSLOT = 0xD7, 0xD8          # {i32 card, i32 slot} drag to the strategy bar / {i32 card, bool8} take out
CLIENT_EVENTS = (START, SELECT, PLAY, PASS, CANCEL, CLOSE, SLOT, UNSLOT)
OPTION_TYPE = 10
PARLEY_OPTION_ID = 9001
MIDDLE, BAR_MAX = 11, 21
EXPRESSION_IDS = {"demand": 0x11, "reason": 0x12, "inspire": 0x13, "flatter": 0x14}
# 0x330 error codes for "not enough <expression>".
NOT_ENOUGH = {"inspire": 7, "reason": 8, "flatter": 9, "demand": 10}
ERR_NOT_PREPARED, ERR_REFRESHING, ERR_NO_CARD, ERR_NOT_YOUR_TURN, ERR_OVER = 4, 5, 6, 0xC, 0xF
POOL_ORDER = ("inspire", "reason", "flatter", "demand")     # 0x31d / 0x32c pairs (mine, theirs)
PARLEY_TYPES = {"entertain": 0, "convince": 1, "interview": 2, "gossip": 3, "incite": 4}


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def civic_update(stat, now, delta):
    """0x33d MsgCivicDiplomacyUpdateStat {wstr stat, i32 now, i32 delta} (FUN_005518f0): "You have
    increased %1 by %2. It is now %3." (decreased when delta < 0; VGClient.int CivicDiplomacyVarInc/Dec)."""
    return _event(0x33D, _w(stat) + struct.pack("<ii", now, delta))


def refresh_timer(cid, left, total):
    """0x266 MsgIntAndTwoFloats {i32 card, f32 rounds left, f32 total} (FUN_0054e1a0): the card's
    refresh count on the strategy bar (card +0x70; 0 = ready)."""
    return _event(0x266, struct.pack("<iff", cid, float(left), float(total)))


def refresh_clear():
    """0x267: every card refreshed (FUN_0054d060)."""
    return _event(0x267)


def card(cid, c, icon=443):
    """MsgAbilityParlayCard from a diplomacy.json card."""
    cost, gain = c.get("cost", {}), c.get("gain", {})
    push = c.get("push", 0)
    results = [gain.get("reason", 0), 0, gain.get("inspire", 0), 0,
               gain.get("flatter", 0), 0, gain.get("demand", 0), 0]
    return (struct.pack("<i", cid) + _w(c["name"]) + struct.pack("<iiii", 0, c.get("icon", icon), push, push)
            + struct.pack("<BBBB", cost.get("reason", 0), cost.get("inspire", 0),
                          cost.get("flatter", 0), cost.get("demand", 0))
            + struct.pack("<8i", *results)
            + struct.pack("<BBB", 0, 0, 0) + _w("")
            + struct.pack("<iii", 0, EXPRESSION_IDS[c.get("expression", "reason")], 0) + struct.pack("<B", 1)
            + struct.pack("<3i", -1, -1, -1))


def deck_messages(cards, deck, slots, resend=False):
    """Deck (all the character's cards) and strategy slots (slots[n] = card id or
    None), sent when a parley starts: a client UI rebuild after login empties the
    card lists, so cards sent at login don't show. On a later parley the old slot
    entries are removed first (0x239), or the same card in the same slot is ignored."""
    out = [_event(0x239, struct.pack("<iB", cid, 1)) for cid in deck] if resend else []
    out += [_event(0x331, struct.pack("<i", len(slots))), _event(0x21C),
            _event(0x21F, struct.pack("<i", len(deck)) + b"".join(card(cid, cards[str(cid)]) for cid in deck))]
    out += [_event(0x237, struct.pack("<ii", cid, n)) for n, cid in enumerate(slots) if cid is not None]
    return out


def slotted(cid, slot):
    """0x237: card cid is now in strategy slot `slot` (reply to 0xd7)."""
    return _event(0x237, struct.pack("<ii", cid, slot))


def unslotted(cid):
    """0x239: card cid left its slot (reply to 0xd8)."""
    return _event(0x239, struct.pack("<iB", cid, 1))


def default_slots(deck, count):
    return [deck[n] if n < len(deck) else None for n in range(count)]


class Parley:
    """One parley's state: the bar, both sides' expression pools and dialog points."""

    def __init__(self, config, cards, deck):
        self.config, self.cards, self.deck = config, cards, deck
        self.status = MIDDLE
        self.mine = dict.fromkeys(POOL_ORDER, 0)
        self.theirs = dict.fromkeys(POOL_ORDER, 0)
        for k, v in config.get("npc_pools", {}).items():
            self.theirs[k] = v
        self.dp = self.opp_dp = 0
        self.round = 0
        self.card = None
        self.refresh = {}               # card id -> rounds left before it can be played again

    def pools(self):
        """The 8 pool bytes in wire order: mine, theirs per expression."""
        return bytes(max(0, min(255, p[k])) for k in POOL_ORDER for p in (self.mine, self.theirs))

    def check(self, cid):
        """0x330 error code if the player can't play this card, else None."""
        c = self.cards.get(str(cid))
        if c is None or cid not in self.deck:
            return ERR_NOT_PREPARED
        if self.refresh.get(cid, 0) > 0:
            return ERR_REFRESHING
        for k, n in c.get("cost", {}).items():
            if self.mine[k] < n:
                return NOT_ENOUGH[k]
        return None

    def _apply(self, c, pools, sign):
        for k, n in c.get("cost", {}).items():
            pools[k] -= n
        for k, n in c.get("gain", {}).items():
            pools[k] += n
        self.status = max(0, min(BAR_MAX, self.status + sign * c.get("push", 0)))

    def play(self, cid):
        self._apply(self.cards[str(cid)], self.mine, +1)
        self.dp += 1
        if self.cards[str(cid)].get("refresh"):
            self.refresh[cid] = self.cards[str(cid)]["refresh"] + 1   # this round's tick takes one

    def tick_refresh(self):
        """A new round: every refreshing card counts down. Returns the 0x266 messages."""
        out = []
        for cid in list(self.refresh):
            self.refresh[cid] -= 1
            out.append(refresh_timer(cid, self.refresh[cid], self.cards[str(cid)]["refresh"]))
            if self.refresh[cid] <= 0:
                del self.refresh[cid]
        return out

    def npc_turn(self, rng=random):
        """The NPC plays an affordable card (usually its strongest). Returns its id."""
        options = [cid for cid in self.config["npc_cards"]
                   if all(self.theirs[k] >= n for k, n in self.cards[str(cid)].get("cost", {}).items())]
        if not options:
            self.round += 1
            return None                 # nothing affordable: the NPC passes
        options.sort(key=lambda cid: -self.cards[str(cid)].get("push", 0))
        cid = options[0] if rng.random() < 0.6 else rng.choice(options)
        self._apply(self.cards[str(cid)], self.theirs, -1)
        self.opp_dp += 1
        self.round += 1
        return cid

    def line(self):
        lines = self.config.get("lines", ["Hmm."])
        return lines[min(self.round - 1, len(lines) - 1)]

    def outcome(self):
        """'won', 'lost' or None."""
        if self.status >= self.config.get("win_at", 17):
            return "won"
        if self.status <= self.config.get("lose_at", 4):
            return "lost"
        return None


def open_parley(npc_eid, p):
    return _event(0x31D, struct.pack("<QBBB", npc_eid, p.status, p.dp, p.opp_dp) + p.pools()
                  + struct.pack("<B", PARLEY_TYPES.get(p.config.get("type", "entertain"), 0)) + _w(""))


def selected(cid):
    return _event(0x332, struct.pack("<i", cid))


def update(p):
    return _event(0x32C, bytes([p.status]) + p.pools())


def points(p):
    return _event(0x337, struct.pack("<ii", p.dp, p.opp_dp))


def round_messages(p, npc_cid):
    """After the player's card (already applied and shown with update/points)
    the NPC answers with npc_cid, then it is the player's turn again."""
    npc_card = [_event(0x218, card(npc_cid, p.cards[str(npc_cid)]))] if npc_cid is not None else []
    return ([_event(0x333)] + npc_card
            + [_event(0x325, _w(p.line())), update(p), points(p), _event(0x256), _event(0x334)])


def error(code, arg=0):
    return _event(0x330, struct.pack("<ii", code, arg))


def won():
    return _event(0x324)


def lost():
    return _event(0x31F, struct.pack("<B", 0))


def ended():
    return [_event(0x31E), _event(0x338)]


def close():
    return _event(0x338)
