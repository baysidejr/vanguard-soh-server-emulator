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
import time

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
        self.died_at = None

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


def play_animation(who, anim, arg=0):
    """0x2e (handler FUN_0061fd10 -> pawn FUN_00bbb490): animation ids resolve
    through FUN_00bb33e0. who = an Npc or an entity id."""
    eid = who if isinstance(who, int) else who.entity_id
    return struct.pack("<HIIQii", 2, ANIM_EVENT, 16, eid, anim, arg)


RELEASE_EVENTS = (0x542,)    # client -> server, no payload: "Release to Bind"
DEATH_POPUP_EVENT = 0x540    # MsgIntAndBool (FUN_005e70b0): "DeathReleasePopup"


def death_popup(seconds, show=True):
    return struct.pack("<HIIiB", 2, DEATH_POPUP_EVENT, 5, seconds, int(show))


DISPLAY_EVENT = 0x3D1        # MsgDisplayAbility (FUN_00439510): play an ability's visuals
PHASE_MISS, PHASE_HIT, PHASE_CRIT, PHASE_BLOCK, PHASE_DODGE, PHASE_PARRY = 0, 2, 3, 4, 5, 6
NPC_AUTO_ATTACK = 9          # MELEE_ABILITIES_9 GENERIC_NPC_AUTO_ATTACK
NO_ENTITY = 0xFFFFFFFFFFFFFFFF
_display_ids = iter(range(1, 1 << 31))


def display_ability(caster, target, visual_id, phase=PHASE_HIT, instance=None):
    """0x3d1 (57 bytes): the client looks visual_id up as an Ability object in
    Assets/Abilities (FUN_007f3640, e.g. 570001 -> WAR_ABILITIES_570001) and plays
    the Actions of the record for this phase on the caster and the target.
    caster/target are entity ids (target NO_ENTITY for none)."""
    display = next(_display_ids)
    data = struct.pack("<QQiiiiBBBBiiBBBBBfi", caster, target, visual_id, display,
                       display if instance is None else instance, -1,
                       0, 0, 0, 0, 0, 0, phase, 0, 0, 0, 0, 0.0, 0)
    return struct.pack("<HII", 2, DISPLAY_EVENT, len(data)) + data


# Visual (Assets/Abilities export number) for each ability id in the book.
ABILITY_VISUALS = {1001: 570001,   # BRUTAL_STRIKE_I
                   1002: 570022,   # SHIELD_BASH_I
                   1003: 570043,   # LIFE_REND_I
                   1004: 570015}   # SHOUT_FURY_I


# Damage range per ability id (MsgAbilityInfo field 20); 0 = no damage (buffs, shouts).
ABILITY_DAMAGE = {1001: (8, 14), 1002: (5, 9), 1003: (12, 20), 1004: (0, 0)}


def use_ability(player, ability, rng=random):
    """ability = a DEFAULT_ABILITIES tuple. Returns [(text, colour kind)], where
    kind is 'combat', 'error' or 'white', and the NPC that changed (or None).
    Visual effects to send are appended to player.pending_displays."""
    name = ability[2]
    if player.health <= 0:
        return [("You can't do that while dead.", "error")], None
    npc = player.npcs.get(player.target) if player.target else None
    if npc is None:
        return [(f"You use {name}, but you have no target.", "combat")], None
    if not npc.alive:
        return [(f"{npc.name} is already dead.", "error")], None
    lo, hi = ABILITY_DAMAGE.get(ability[1], (6, 10))
    visual = ABILITY_VISUALS.get(ability[1])
    if hi == 0:
        if visual:
            player.pending_displays.append(display_ability(player.char_id, NO_ENTITY, visual))
        return [(f"You use {name}.", "combat")], None
    if visual:
        player.pending_displays.append(display_ability(player.char_id, npc.entity_id, visual))
    dmg = rng.randint(lo, hi)
    npc.health = max(npc.health - dmg, 0)
    player.last_combat = time.time()
    if not npc.alive:
        npc.died_at = time.time()
    lines = [(f"Your {name} hits {npc.name} for {dmg} damage.", "combat")]
    if not npc.alive:
        lines.append((f"You have slain {npc.name}!", "white"))
    else:
        lines += npc_attacks(player, npc, rng)
    return lines, npc


NPC_DAMAGE = (3, 9)


def npc_attacks(player, npc, rng=random):
    """The NPC strikes back once. Lowers player.health (the HUD bar follows a
    0x2d4 update of the Health stat; see zone.health_update)."""
    if player.health <= 0:
        return []
    dmg = rng.randint(*NPC_DAMAGE)
    player.pending_displays.append(display_ability(npc.entity_id, player.char_id, NPC_AUTO_ATTACK))
    player.health = max(player.health - dmg, 0)
    lines = [(f"{npc.name} hits YOU for {dmg} damage.", "error")]
    if player.health == 0:
        lines.append(("You have been slain!", "error"))
    return lines


RESPAWN_SECONDS = 30
REGEN_DELAY = 6          # seconds out of combat before health comes back
REGEN_PER_SECOND = 10


def tick(player, now):
    """Once a second: returns ('health',) when the player's health changed and
    ('respawn', npc) for NPCs that come back."""
    out = []
    if 0 < player.health < player.stats["hit_points"] and now - player.last_combat >= REGEN_DELAY:
        player.health = min(player.health + REGEN_PER_SECOND, player.stats["hit_points"])
        out.append(("health",))
    for npc in player.npcs.values():
        if npc.died_at and now - npc.died_at >= RESPAWN_SECONDS:
            npc.health, npc.died_at = npc.max_health, None
            out.append(("respawn", npc))
    return out
