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
import math
import random
import struct
import time

TARGET_EVENT = 0x5D          # client -> server: u64 entity id
TARGET_HEALTH_EVENT = 0x3E1  # server -> client: u64 entity id, u8 health
TARGETS_EVENT = 0x3E0        # server -> client: offensive, defensive, third target


class Npc:
    def talks(self):
        """Opens a dialogue when used or hailed."""
        return bool(self.merchant or self.quests or self.trainer or self.banker or self.parley or self.repairs)

    def service(self):
        """A vendor, trainer, node, station...: can't be attacked."""
        return bool(self.talks() or self.harvest or self.station or self.prop)

    def __init__(self, entity_id, name, channel, cls_path, max_health=100, location=(0.0, 0.0, 0.0)):
        self.entity_id = entity_id
        self.name = name
        self.channel = channel        # UE2 actor channel of its pawn
        self.cls_path = cls_path
        self.max_health = max_health
        self.health = max_health
        self.died_at = None
        self.location = location
        self.home = location
        self.loot = None              # items left on the corpse (None = not rolled yet)
        self.aggro = False            # chasing aggro_on
        self.aggro_on = None          # the zone.Player it fights
        self.moving = False
        self.next_attack = 0.0
        self.death_shown = False      # death already broadcast
        self.race = 0
        self.gear = []
        self.yaw = 0
        self.level = 1
        self.stance = False           # weapons drawn (m_CombatState)
        self.wander = 0.0             # stroll radius around home (0 = stand still)
        self.path = []                # patrol waypoints [(x, y)], walked in a loop
        self.path_index = 0
        self.path_pause = 2.0         # seconds standing at each waypoint
        self.wander_goal = None       # (x, y) it is walking to
        self.next_wander = 0.0
        self.ground_z = None          # f(x, y) -> standing z (terrain)
        self.quests = []              # quest keys this NPC gives (content/quests.json)
        self.template_id = None
        self.merchant = None
        self.harvest = None           # resource node settings (mobs.json "harvest")
        self.depleted_until = 0.0
        self.station = False          # crafting station (mobs.json "station")
        self.trainer = False          # ability trainer (mobs.json "trainer")
        self.abilities = []           # special attacks (mobs.json "abilities")
        self.prop = False             # scenery (mobs.json "prop"): can't be attacked
        self.banker = False           # bank access (mobs.json "banker")
        self.repairs = False          # repairs gear (mobs.json "repair")
        self.parley = False           # offers a diplomacy parley (mobs.json "parley")          # merchants.json list id (vendors can't be attacked)
        self.attack_visual = NPC_AUTO_ATTACK
        self.aggro_radius = 0.0       # attacks players that come this close (0 = only if hit)
        self.props = {}               # extra replicated pawn properties from the template
        self.damage = NPC_DAMAGE
        self.respawn = 60             # seconds after death
        self.loot_table = None        # content/loot.json table id
        self.roll_loot = None         # content.Content.roll_loot

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
CREATURE_AUTO_ATTACK = 27    # MELEE_ABILITIES_27 GENERIC_NPC_CREATURE_AUTO_ATTACK
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
    if npc.service():
        return [(f"You can't attack {npc.name}.", "error")], None
    cost = ABILITY_COST if ability[5] > 0 else 0      # instant openers are free
    if player.endurance < cost:
        return [("You do not have enough endurance.", "error")], None
    player.endurance -= cost
    player.endurance_changed = True
    lo, hi = ABILITY_DAMAGE.get(ability[1], (8, 16))
    # Class abilities use their Assets/Abilities id directly (class_abilities.py).
    visual = ABILITY_VISUALS.get(ability[1], ability[1] if ability[1] >= 500000 else None)
    if hi == 0:
        if visual:
            player.pending_displays.append(display_ability(player.char_id, NO_ENTITY, visual))
        return [(f"You use {name}.", "combat")], None
    return strike(player, npc, f"Your {name}", visual, lo, hi, rng)


AUTO_ATTACK_VISUAL = 0       # MELEE_ABILITIES_0 GENERIC_AUTO_ATTACK
AUTO_ATTACK_DAMAGE = (4, 9)
AUTO_ATTACK_SECONDS = 2.0


def strike(player, npc, what, visual, lo, hi, rng=random):
    """One hit on npc ("<what> hits <npc> for N damage."); the NPC answers if it
    survives."""
    if visual is not None:
        player.pending_displays.append(display_ability(player.char_id, npc.entity_id, visual))
    dmg = rng.randint(lo, hi)
    npc.health = max(npc.health - dmg, 0)
    player.last_combat = time.time()
    verb = "hit" if what == "You" else "hits"
    lines = [(f"{what} {verb} {npc.name} for {dmg} damage.", "combat")]
    if not npc.alive:
        npc.died_at = time.time()
        player.auto_attack = False
        lines.append((f"You have slain {npc.name}!", "white"))
        player.pending_rewards.append(KILL_XP)
    else:
        npc.aggro, npc.aggro_on = True, player   # fights back from the tick (npc_turns)
    return lines, npc


KILL_XP = 150
XP_EVENT = 0x3D5             # MsgExperienceRewardResult (FUN_005e3510)


def experience_reward(amount, source, rest_bonus=0, kind=0, group=0):
    """0x3d5: i32 amount, i32 rest bonus, u8 kind (0 adventuring, 1 crafting,
    2 diplomacy), u8 group (0 solo, 1 group, 2 brotherhood, 3 raid), bool8
    "recover" instead of "gain", u64 source entity, bool8/bool8 XP-capped
    (class/race). Prints "You gain N adventuring experience!"."""
    data = struct.pack("<iiBBBQBB", amount, rest_bonus, kind, group, 0, source, 0, 0)
    return struct.pack("<HII", 2, XP_EVENT, len(data)) + data


def toggle_auto_attack(player):
    """Client event 0x3d8. Returns chat lines; player.auto_attack is the new state."""
    npc = player.npcs.get(player.target) if player.target else None
    if not player.auto_attack and (npc is None or not npc.alive or npc.merchant or npc.harvest
                                   or player.health <= 0):
        return [("You have no valid target to attack.", "error")]
    player.auto_attack = not player.auto_attack
    player.next_swing = time.time()
    return []


def auto_attack_state(on):
    """0x3df MsgSingleBool (FUN_005e26a0): Begin/StopAutoattacking; plus 0x3c2
    MsgSingleByte bInCombat (FUN_005e1660)."""
    return [struct.pack("<HIIB", 2, 0x3DF, 1, int(on)), struct.pack("<HIIB", 2, 0x3C2, 1, int(on))]


NPC_DAMAGE = (3, 9)
NPC_ATTACK_SECONDS = 2.5


def npc_turns(player, now, rng=random):
    """Aggressive NPCs in melee range attack. Returns [(lines, npc)]."""
    out = []
    pos = getattr(player, "live_position", None)
    for npc in player.npcs.values():
        if not (npc.alive and npc.aggro and npc.aggro_on is player) or now < npc.next_attack:
            continue
        if player.health <= 0:
            npc.aggro, npc.aggro_on, npc.moving = False, None, False
            continue
        if pos and math.hypot(pos[0] - npc.location[0], pos[1] - npc.location[1]) > MELEE_RANGE + 40:
            continue
        npc.next_attack = now + NPC_ATTACK_SECONDS
        player.last_combat = now
        out.append((npc_attacks(player, npc, rng), npc))
    return out


def npc_attacks(player, npc, rng=random):
    """The NPC strikes once. Lowers player.health (the HUD bar follows a
    0x2d4 update of the Health stat; see zone.health_update)."""
    if player.health <= 0:
        return []
    npc.aggro, npc.aggro_on = True, player
    dmg = rng.randint(*npc.damage)
    player.pending_displays.append(display_ability(npc.entity_id, player.char_id, npc.attack_visual))
    player.health = max(player.health - dmg, 0)
    lines = [(f"{npc.name} hits YOU for {dmg} damage.", "error")]
    if player.health == 0:
        lines.append(("You have been slain!", "error"))
    return lines


NPC_SPEED = 220.0            # units per second while chasing
MELEE_RANGE = 90.0


def move_toward(npc, target, dt, speed, stop_at):
    """Step npc toward target (x, y); returns the replicated properties, or None
    when it was already standing within stop_at."""
    dx, dy = target[0] - npc.location[0], target[1] - npc.location[1]
    dist = math.hypot(dx, dy)
    yaw = int(math.degrees(math.atan2(dy, dx)) * 65536 / 360) & 0xFFFF if dist > 1 else npc.yaw
    if dist <= stop_at:
        if not npc.moving:
            return None
        npc.moving = False
        npc.yaw = yaw
        return {"Velocity": (0.0, 0.0, 0.0), "Rotation": (0, yaw, 0),
                "PawnPosition": (npc.location, (0, yaw, 0), (0.0, 0.0, 0.0))}
    step = min(speed * dt, dist - stop_at)
    z = npc.location[2]
    if npc.ground_z:
        z = npc.ground_z(npc.location[0] + dx / dist * step, npc.location[1] + dy / dist * step)
    npc.location = (npc.location[0] + dx / dist * step, npc.location[1] + dy / dist * step, z)
    npc.moving, npc.yaw = True, yaw
    vel = (dx / dist * speed, dy / dist * speed, 0.0)
    # PawnPosition also resets the client's ground-stick cache (see zone.py).
    return {"Location": npc.location, "Rotation": (0, yaw, 0), "Velocity": vel,
            "PawnPosition": (npc.location, (0, yaw, 0), vel)}


WANDER_SPEED = 90.0          # a stroll
WANDER_PAUSE = (4.0, 12.0)   # seconds standing between strolls
LEASH = 1500.0               # an NPC chasing further than this from home gives up


def chase_step(npc, target, dt, rng=random, now=None):
    """One movement step for an NPC: chase its attacker (target = x, y, z), walk
    home after losing it, or wander around home within npc.wander. Returns the
    replicated properties to send, or None."""
    if not npc.alive:
        return None
    now = time.time() if now is None else now
    if npc.aggro and target is not None:
        if math.hypot(npc.location[0] - npc.home[0], npc.location[1] - npc.home[1]) > LEASH:
            npc.aggro, npc.aggro_on, npc.wander_goal = False, None, npc.home
        else:
            return move_toward(npc, target, dt, NPC_SPEED, MELEE_RANGE)
    if npc.wander_goal is not None:
        values = move_toward(npc, npc.wander_goal, dt,
                             NPC_SPEED if npc.wander_goal == npc.home else WANDER_SPEED, 5.0)
        if not npc.moving:
            pause = npc.path_pause if npc.path else rng.uniform(*WANDER_PAUSE)
            npc.wander_goal, npc.next_wander = None, now + pause
        return values
    if npc.path and now >= npc.next_wander:
        npc.wander_goal = tuple(npc.path[npc.path_index])
        npc.path_index = (npc.path_index + 1) % len(npc.path)
        return None
    if npc.wander > 0 and now >= npc.next_wander:
        angle, r = rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 1.0) * npc.wander
        npc.wander_goal = (npc.home[0] + r * math.cos(angle), npc.home[1] + r * math.sin(angle))
    return None


RESPAWN_SECONDS = 60
REGEN_DELAY = 6          # seconds out of combat before health comes back
REGEN_PER_SECOND = 10
ABILITY_COST = 15            # endurance per ability use (placeholder)
ENDURANCE_REGEN = 4          # per second, in and out of combat


def respawns(npcs, now):
    """NPCs (of one world) that come back to life now."""
    back = []
    for npc in npcs.values():
        if npc.died_at and now - npc.died_at >= npc.respawn:
            npc.health, npc.died_at = npc.max_health, None
            npc.aggro, npc.aggro_on, npc.moving = False, None, False
            npc.location, npc.loot, npc.wander_goal = npc.home, None, None
            back.append(npc)
    return back


def tick(player, now):
    """Once a second for one player: auto-attack swings ('swing', lines, npc) and
    regeneration ('health',)."""
    out = []
    if player.auto_attack and now >= player.next_swing:
        player.next_swing = now + AUTO_ATTACK_SECONDS
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.alive or player.health <= 0:
            player.auto_attack = False
            out.append(("swing", [], None))
        else:
            out.append(("swing", *strike(player, npc, "You", AUTO_ATTACK_VISUAL,
                                         *AUTO_ATTACK_DAMAGE)))
    if player.health > 0 and player.endurance < player.stats["endurance"]:
        player.endurance = min(player.endurance + ENDURANCE_REGEN, player.stats["endurance"])
        out.append(("endurance",))
    if 0 < player.health < player.stats["hit_points"] and now - player.last_combat >= REGEN_DELAY:
        regen = REGEN_PER_SECOND * (3 if getattr(player, "resting", False) else 1)
        player.health = min(player.health + regen, player.stats["hit_points"])
        out.append(("health",))
    return out


LOOT_OPEN_EVENT = 0x1E8      # S->C MsgEntityIDAndBool (FUN_00520be0): begin looting, open "_loot"
LOOT_ITEM_EVENT = 0x1F2      # S->C MsgSingleItemInfo: add one item to the loot list (no UI yet)
LOOT_READY_EVENT = 0x1EF     # S->C no payload (FUN_00521370): list complete, fill the window rows
LOOT_TAKEN_EVENT = 0x1F6     # S->C MsgIntAndBool {i32 handle, bool notify}: "You loot X", row removed
LOOT_END_EVENT = 0x1ED       # S->C no payload (FUN_00521270): loot session over
LOOT_REQUEST = 0xBB          # C->S u64 corpse eid (U key, FUN_005203d0)
LOOT_TAKE = 0xBC             # C->S i32 item handle (field 71)
LOOT_TAKE_ALL = 0xBD         # C->S i32 -1 ("Take All")
LOOT_CLOSE = 0xBE            # C->S no payload

# Placeholder loot: (item id = handle, name, icon, quantity).
LOOT_TABLE = [(5001, "Tattered Cloth", 442, 2), (5002, "Rough Stone", 443, 1),
              (5003, "Copper Ring", 472, 1)]


def zone_item_fields(name):
    import zone
    return zone.item_equip_fields(name)


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def loot_messages(npc):
    """Open the loot window on a corpse: 0x1ed (clear), 0x1e8, one 0x1f2 per item,
    then 0x1ef, which builds the rows (docs/LOOT.md)."""
    import vgmsg
    if npc.loot is None:
        if npc.roll_loot and npc.loot_table:
            npc.loot = [(5001 + n, name, icon, qty)
                        for n, (name, icon, qty) in enumerate(npc.roll_loot(npc.loot_table))]
        else:
            npc.loot = list(LOOT_TABLE)
    out = [_event(LOOT_END_EVENT), _event(LOOT_OPEN_EVENT, struct.pack("<QB", npc.entity_id, 1))]
    for slot, (item_id, name, icon, qty) in enumerate(npc.loot):
        out.append(_event(LOOT_ITEM_EVENT, vgmsg.inventory_item(item_id, name, slot, icon=icon,
                                                               quantity=qty, **zone_item_fields(name))))
    out.append(_event(LOOT_READY_EVENT))
    return out


def take_loot(player, npc, handle):
    """Move loot items (handle -1 = all) into the player's bag. Returns messages."""
    import vgmsg
    out = []
    for item in [i for i in (npc.loot or []) if handle in (-1, i[0])]:
        item_id, name, icon, qty = item
        import zone
        slot = zone.free_bag_slot(player)
        if slot is None:
            break           # bags full: the item stays on the corpse
        npc.loot.remove(item)
        # Each item in the bag needs its own id (it is also the client's handle).
        new_id = zone.new_item_id(player)
        player.items.append((new_id, name, icon, qty, slot))
        out.append(_event(0x197, vgmsg.inventory_item(new_id, name, slot, icon=icon, quantity=qty,
                                                            **zone_item_fields(name))))
        out.append(_event(LOOT_TAKEN_EVENT, struct.pack("<iB", item_id, 1)))
    if not npc.loot:
        out.append(_event(LOOT_END_EVENT))
    return out


CONSIDER_REQUEST = 0x3D9     # client, no payload (/con on the current target)
CONSIDER_RESULT = 0x3DA      # MsgConsiderResult (FUN_005e7670)


def consider(player, npc):
    """0x3da {i32 kind 0 (combat), i32 con 0..7, i32 difficulty 0..5, i32 level,
    wstr name, wstr}. con: 0 trivial ... 4 fair fight ... 7 "Do you have a
    deathwish?"; chosen from the level difference."""
    diff = npc.level - player.level_number
    con = 4 if diff == 0 else max(0, min(7, 4 + (diff // 2 if diff > 0 else -((-diff + 1) // 2))))
    data = struct.pack("<iiii", 0, con, 1, npc.level)
    data += (npc.name + "\0").encode("utf-16-le") + "\0".encode("utf-16-le")
    return struct.pack("<HII", 2, CONSIDER_RESULT, len(data)) + data


def proximity_aggro(npc, players):
    """An aggressive NPC picks the nearest living player inside its aggro radius.
    Returns that player when it starts a fight, else None."""
    if npc.aggro or not npc.alive or npc.aggro_radius <= 0 or npc.merchant or npc.harvest:
        return None
    best = None
    for p in players:
        pos = p.live_position or p.spawned_at
        if pos is None or p.health <= 0:
            continue
        d = math.hypot(pos[0] - npc.location[0], pos[1] - npc.location[1])
        if d <= npc.aggro_radius and (best is None or d < best[0]):
            best = (d, p)
    if best:
        npc.aggro, npc.aggro_on = True, best[1]
        return best[1]
    return None
