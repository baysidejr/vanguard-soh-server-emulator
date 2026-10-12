"""Targeting and a first, very simple combat loop.

Client event 0x5d (u64 entity id) asks for a target; the client draws the
selection ring itself. The server confirms it with zone event 0x3e0
MsgPlayerCharacterUpdate (handler FUN_005e7df0): offensive target (u64 entity
id, u8 health), defensive target (u64, u8), a third (u64, u8); FUN_004cff30
stores the offensive target. Zone event 0x3e1 MsgEntityIDAndByte
(u64 entity id, u8 health 0..255; handler FUN_005ea760) sets the target window's
health bar ("OffTargetLifePoints" = byte * 100 / 255). The client ignores it
unless the id is its current offensive target.

Damage numbers are placeholders: there are no real combat formulas yet."""
import random
import struct

TARGET_EVENT = 0x5D          # client -> server: u64 entity id
TARGET_HEALTH_EVENT = 0x3E1  # server -> client: u64 entity id, u8 health
TARGETS_EVENT = 0x3E0        # server -> client: offensive, defensive, third target


class Npc:
    def __init__(self, entity_id, name, channel, cls_path, max_health=100):
        self.entity_id = entity_id
        self.name = name
        self.channel = channel        # UE2 actor channel of its pawn
        self.cls_path = cls_path
        self.max_health = max_health
        self.health = max_health

    @property
    def alive(self):
        return self.health > 0

    def health_byte(self):
        return round(255 * max(self.health, 0) / self.max_health)


def target_health(npc):
    return struct.pack("<HIIQB", 2, TARGET_HEALTH_EVENT, 9, npc.entity_id, npc.health_byte())


def targets(offensive=None, defensive=None):
    """0x3e0: the targets the server accepts (None = no target)."""
    data = b""
    for npc in (offensive, defensive, None):
        data += struct.pack("<QB", npc.entity_id, npc.health_byte()) if npc else struct.pack("<QB", 0, 0)
    return struct.pack("<HII", 2, TARGETS_EVENT, len(data)) + data


ANIM_EVENT = 0x2E             # server -> client: u64 entity id, i32 animation, i32 arg
ANIM_DEATH = 1               # FUN_00bbb490: 1..3 are death animations (pawn stays down)


def play_animation(npc, anim, arg=0):
    """0x2e (handler FUN_0061fd10 -> pawn FUN_00bbb490): animation ids resolve
    through FUN_00bb33e0."""
    return struct.pack("<HIIQii", 2, ANIM_EVENT, 16, npc.entity_id, anim, arg)


# Damage range per ability id (MsgAbilityInfo field 20); 0 = no damage (buffs, shouts).
ABILITY_DAMAGE = {1001: (8, 14), 1002: (5, 9), 1003: (12, 20), 1004: (0, 0)}


def use_ability(player, ability, rng=random):
    """ability = a DEFAULT_ABILITIES tuple. Returns [(text, colour kind)], where
    kind is 'combat', 'error' or 'white', and the NPC that changed (or None)."""
    name = ability[2]
    npc = player.npcs.get(player.target) if player.target else None
    if npc is None:
        return [(f"You use {name}, but you have no target.", "combat")], None
    if not npc.alive:
        return [(f"{npc.name} is already dead.", "error")], None
    lo, hi = ABILITY_DAMAGE.get(ability[1], (6, 10))
    if hi == 0:
        return [(f"You use {name}.", "combat")], None
    dmg = rng.randint(lo, hi)
    npc.health = max(npc.health - dmg, 0)
    lines = [(f"Your {name} hits {npc.name} for {dmg} damage.", "combat")]
    if not npc.alive:
        lines.append((f"You have slain {npc.name}!", "white"))
    return lines, npc
