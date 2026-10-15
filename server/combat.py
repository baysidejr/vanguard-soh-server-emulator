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

import effects

TARGET_EVENT = 0x5D          # client -> server: u64 entity id
TARGET_HEALTH_EVENT = 0x3E1  # server -> client: u64 entity id, u8 health
TARGETS_EVENT = 0x3E0        # server -> client: offensive, defensive, third target


class Npc:
    def talks(self):
        """Opens a dialogue when used or hailed."""
        return bool(self.merchant or self.quests or self.trainer or self.banker or self.parley or self.repairs
                    or getattr(self, "task_master", False) or getattr(self, "recipe_trainer", None)
                    or getattr(self, "broker", None) or getattr(self, "dialog", None)
                    or getattr(self, "assembly_trainer", None))

    def service(self):
        """A vendor, trainer, node, station...: can't be attacked."""
        return bool(self.talks() or self.harvest or self.station or self.prop
                    or getattr(self, "pet_owner", None) is not None)

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
        self.aggro_on = None          # the zone.Player it fights (the top of its hate list)
        self.hate = {}                # char_id -> [player, hate]: damage done to it
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
        self.blocked = None           # f(x, y, z) -> True inside a rock, tree, wall ... (obstacles.py)
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
        self.coin = None              # mobs.json "coin" [min, max] copper (None: by level)
        self.spells = []              # mobs.json "spells": [{name, cast, damage, chance, icon}]
        self.casting = None           # the spell being cast (login_stub.npc_cast)
        self.coin_left = None         # copper still on the corpse (None = not rolled yet)
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
        if npc is None:
            data += struct.pack("<QB", 0, 0)
        elif hasattr(npc, "health_byte"):
            data += struct.pack("<QB", npc.entity_id, npc.health_byte())
        else:                                   # a player (defensive target)
            hp = npc.stats["hit_points"] or 1
            data += struct.pack("<QB", npc.char_id, max(0, min(255, npc.health * 255 // hp)))
    return struct.pack("<HII", 2, TARGETS_EVENT, len(data)) + data


ANIM_EVENT = 0x2E             # server -> client: u64 entity id, i32 animation, i32 arg
ANIM_DEATH = 1               # FUN_00bbb490: 1..3 are death animations (pawn stays down)


def play_animation(who, anim, arg=0):
    """0x2e (handler FUN_0061fd10 -> pawn FUN_00bbb490): animation ids resolve
    through FUN_00bb33e0. who = an Npc or an entity id."""
    eid = who if isinstance(who, int) else who.entity_id
    return struct.pack("<HIIQii", 2, ANIM_EVENT, 16, eid, anim, arg)


# client -> server, no payload: 0x541 Release (popup bool 0), 0x542 release to bind,
# 0x543 release to altar (popup bool 1, FUN_005e70b0)
RELEASE_EVENTS = (0x541, 0x542, 0x543)
DEATH_POPUP_EVENT = 0x540    # MsgIntAndBool (FUN_005e70b0): "DeathReleasePopup"


def death_popup(seconds, show=True):
    """0x540 {i32 seconds, bool8 kind}: kind 1 = Release to Bind / Release to Altar popup, 0 = a single
    Release button; seconds <= 0 closes the popup of that kind."""
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
# Ability power (placeholders): +8% per level above 1, and +1% per point of the class's
# main attribute above its default (Strength for fighters, Intelligence for casters'
# damage, Wisdom for heals).
POWER_PER_LEVEL, POWER_PER_POINT = 0.08, 0.01


def power(player, kind="damage"):
    """Multiplier for an ability's damage ("damage") or healing ("heal")."""
    level = getattr(player, "mentor_level", None) or getattr(player, "level_number", 1)
    if kind == "heal":
        stat, base = "wisdom", 20
    elif getattr(player, "klass", None) in ENERGY_CLASSES:
        stat, base = "intelligence", 20
    else:
        stat, base = "strength", 40
    points = getattr(player, "stats", {}).get(stat, base) - base
    return max(0.1, 1 + POWER_PER_LEVEL * (level - 1) + POWER_PER_POINT * points)


def scaled(player, lo_hi, kind="damage"):
    m = power(player, kind)
    return int(round(lo_hi[0] * m)), int(round(lo_hi[1] * m))


def use_ability(player, ability, rng=random):
    """ability = a DEFAULT_ABILITIES tuple. Returns [(text, colour kind)], where
    kind is 'combat', 'error' or 'white', and the NPC that changed (or None).
    Visual effects to send are appended to player.pending_displays."""
    name = ability[2]
    if player.health <= 0:
        return [("You can't do that while dead.", "error")], None
    npc = player.npcs.get(player.target) if player.target else None
    if npc is None:
        return [(NO_VALID_TARGET, "fail")], None             # "Please select a valid target for that ability."
    if not npc.alive:
        return [(f"{npc.name} is already dead.", "error")], None
    if npc.service():
        return [(f"You can't attack {npc.name}.", "error")], None
    error = pay_cost(player, ability[5])
    if error:
        return [(error, "fail")], None
    lo, hi = scaled(player, ABILITY_DAMAGE.get(ability[1], (8, 16)))
    # Class abilities use their Assets/Abilities id directly (class_abilities.py).
    visual = ABILITY_VISUALS.get(ability[1], ability[1] if ability[1] >= 500000 else None)
    if hi == 0:
        if visual:
            player.pending_displays.append(display_ability(player.char_id, NO_ENTITY, visual))
        return [(f"You use {name}.", "combat")], None
    return strike(player, npc, f"Your {name}", visual, lo, hi, rng)


HITS = 3                     # 0x27b damage type: 0 slash, 1 crush, 2 pierce, other "hits"
AUTO_ATTACK_VISUAL = 0       # MELEE_ABILITIES_0 GENERIC_AUTO_ATTACK
AUTO_ATTACK_DAMAGE = (4, 9)        # bare hands, or a weapon without items.json "damage"
STRENGTH_BASE, STRENGTH_PER_POINT = 40, 10   # +1 damage per 10 Strength above 40 (placeholder)


def auto_attack_damage(player):
    """(min, max) of an auto-attack swing: the equipped weapon's items.json damage (primary
    hand or two-hander), plus the Strength bonus."""
    import zone
    lo, hi = AUTO_ATTACK_DAMAGE
    for e in getattr(player, "equipment", []):
        if e[3] in (28, 36):                       # PRIMARYHAND, TWOHANDS
            dmg = zone.ITEM_CONTENT.item(e[1]).get("damage")
            if dmg:
                lo, hi = dmg
                break
    bonus = max(0, (getattr(player, "stats", {}).get("strength", STRENGTH_BASE) - STRENGTH_BASE) // STRENGTH_PER_POINT)
    return lo + bonus, hi + bonus
AUTO_ATTACK_SECONDS = 2.0


# Hit table (placeholder numbers until real data is found; docs/EFFECTS.md "Avoidance").
BASE_MISS, MISS_PER_LEVEL = 0.06, 0.02        # attacker misses; +2% per level the defender is above
BASE_DODGE, DODGE_PER_DEX = 0.04, 0.001       # defender dodges; +0.1% per Dexterity point above 30
BASE_PARRY, BASE_BLOCK = 0.04, 0.06           # with a weapon in hand / a shield equipped
BASE_CRIT, CRIT_PER_DEX, CRIT_MULT = 0.05, 0.001, 1.5


def crit_chance(dex):
    """A melee swing's critical chance (also shown on the character window's Stats tab)."""
    return BASE_CRIT + CRIT_PER_DEX * max(0, dex - 30)


def roll_outcome(rng, attacker_level, defender_level, defender_dex=30, attacker_dex=30,
                 can_parry=False, can_block=False, crit=None):
    """One swing's outcome: effects.MISS / DODGE / PARRY / BLOCK / CRIT / HIT. crit overrides the
    critical chance (mobs.json "crit", 0-1)."""
    r = rng.random()
    for outcome, chance in (
            (effects.MISS, BASE_MISS + MISS_PER_LEVEL * max(0, defender_level - attacker_level)),
            (effects.DODGE, BASE_DODGE + DODGE_PER_DEX * max(0, defender_dex - 30)),
            (effects.PARRY, BASE_PARRY if can_parry else 0.0),
            (effects.BLOCK, BASE_BLOCK if can_block else 0.0),
            (effects.CRIT, crit_chance(attacker_dex) if crit is None else float(crit))):
        if r < chance:
            return outcome
        r -= chance
    return effects.HIT


def strike(player, npc, what, visual, lo, hi, rng=random):
    """One swing at npc ("<what> hits <npc> for N damage.", or a miss, dodge, parry or
    critical hit); the NPC answers if it survives."""
    if visual is not None:
        player.pending_displays.append(display_ability(player.char_id, npc.entity_id, visual))
    outcome = roll_outcome(rng, getattr(player, "level_number", 1), getattr(npc, "level", 1),
                           attacker_dex=getattr(player, "stats", {}).get("dexterity", 30),
                           can_parry=getattr(npc, "race", 0) < 64)          # people parry, creatures don't
    dmg = rng.randint(lo, hi)
    if outcome == effects.CRIT:
        dmg = int(dmg * CRIT_MULT)
    elif outcome != effects.HIT:
        dmg = 0
    npc.health = max(npc.health - dmg, 0)
    player.last_combat = time.time()
    # The client writes the line (0x27b, Combat tab): "You hit Rat for 6 damage." for
    # auto-attack (kind 0, generic verb), "Your Brutal Strike hits Rat ..." for abilities.
    ability = "" if what == "You" else what[len("Your "):]
    player.pending_displays.append(effects.combat_text(player.char_id, npc.entity_id, ability, dmg,
                                                       kind=0 if not ability else 1, dmg_type=HITS,
                                                       outcome=outcome))
    lines = []
    if not npc.alive:
        npc.died_at = time.time()
        npc.killer = player
        player.auto_attack = False
        lines.append((f"You have slain {npc.name}!", "white"))
        player.pending_rewards.append(kill_xp(player, npc))
    else:
        add_hate(npc, player, dmg)                # fights back from the tick (npc_turns)
    return lines, npc


KILL_XP = 150                # experience for a kill at the player's own level (placeholder)
XP_PER_LEVEL_DIFF = 0.15     # +15% per level the NPC is above, -15% per level below
GRAY_LEVELS = 6              # NPCs this many levels below give nothing


def kill_xp(player, npc):
    """Experience for killing npc: scaled by the level difference; trivial kills give 0."""
    diff = getattr(npc, "level", 1) - getattr(player, "level_number", 1)
    if diff <= -GRAY_LEVELS:
        return 0
    return max(1, int(round(KILL_XP * (1 + XP_PER_LEVEL_DIFF * diff))))
XP_EVENT = 0x3D5             # MsgExperienceRewardResult (FUN_005e3510)


def experience_reward(amount, source, rest_bonus=0, kind=0, group=0):
    """0x3d5: i32 amount, i32 rest bonus, u8 kind (0 adventuring, 1 crafting,
    2 diplomacy), u8 group (0 solo, 1 group, 2 brotherhood, 3 raid), bool8
    "recover" instead of "gain", u64 source entity, bool8/bool8 XP-capped
    (class/race). Prints "You gain N adventuring experience!"."""
    data = struct.pack("<iiBBBQBB", amount, rest_bonus, kind, group, 0, source, 0, 0)
    return struct.pack("<HII", 2, XP_EVENT, len(data)) + data


# The client's auto-attack failures: 0x244 {u8 code} (FUN_0042b350) prints VGClient.int
# AutoAttackFail*: 1 "You can't fight with that.", 2 "You don't have a target.", 3 "Your target is
# dead.", 4 "Your target is not valid to attack.", 5 "Your target is out of range.", 6 "You can't
# attack with that type of weapon.", each with a screen flash.
AUTO_ATTACK_FAILED = 0x244
AUTO_NO_TARGET, AUTO_TARGET_DEAD, AUTO_TARGET_INVALID = 2, 3, 4


def auto_attack_failed(code):
    return _event(AUTO_ATTACK_FAILED, struct.pack("<B", code))


def in_combat(player):
    """Auto-attacking, or an NPC is fighting the player (the client's own notices refuse some
    actions then, e.g. 94 CantDestroyItemsInCombat)."""
    if getattr(player, "auto_attack", False):
        return True
    return any(npc.alive and getattr(npc, "aggro", False) and npc.aggro_on is player
               for npc in getattr(player, "npcs", {}).values())


def toggle_auto_attack(player):
    """Client event 0x3d8. Returns chat lines; player.auto_attack is the new state. A refusal is
    an ("autofail", code) line (0x244)."""
    npc = player.npcs.get(player.target) if player.target else None
    opp = getattr(player, "duel_opponent", None)
    if opp is not None and player.target == opp.char_id and player.health > 0:
        npc = opp                                 # dueling: the opponent is a valid target
    if not player.auto_attack:
        if player.health <= 0:
            return [("You can't do that while dead.", "error")]
        if npc is None:
            return [(AUTO_NO_TARGET, "autofail")]
        if not npc.alive:
            return [(AUTO_TARGET_DEAD, "autofail")]
        if isinstance(npc, Npc) and npc.service():       # vendors, stations, props, pets...
            return [(AUTO_TARGET_INVALID, "autofail")]
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
        if not (npc.alive and npc.aggro and npc.aggro_on is player) or now < npc.next_attack or npc.casting:
            continue
        if now < getattr(npc, "feared_until", 0):
            continue                       # running away in terror
        if player.health <= 0:
            npc.aggro, npc.aggro_on, npc.moving = False, None, False
            npc.hate = {}
            continue
        if pos and math.hypot(pos[0] - npc.location[0], pos[1] - npc.location[1]) > MELEE_RANGE + 40:
            continue
        npc.next_attack = now + NPC_ATTACK_SECONDS
        player.last_combat = now
        out.append((npc_attacks(player, npc, rng), npc))
    return out


SWITCH_FACTOR = 1.1          # another attacker must out-hate the current target by 10%


def add_hate(npc, player, amount):
    """Damage (or a taunt) adds hate; the NPC fights the living player it hates most, and
    only changes target when someone passes SWITCH_FACTOR x its current target's hate."""
    entry = npc.hate.setdefault(player.char_id, [player, 0.0])
    entry[1] += amount
    if not npc.aggro:
        npc.pulled = True            # just pulled: may call nearby allies (social_assist)
    npc.aggro = True
    cur = npc.aggro_on
    cur_hate = npc.hate.get(cur.char_id, [cur, 0.0])[1] if cur is not None and cur.health > 0 else -1.0
    if cur is None or cur.health <= 0 or (cur is not player and entry[1] > cur_hate * SWITCH_FACTOR):
        npc.aggro_on = player


ASSIST_RADIUS = 700.0        # allies this close come to help a pulled NPC


def social_assist(npc, npcs):
    """A just-pulled NPC calls for help: alive, idle NPCs of the same faction (or the same
    kind when it has none) within ASSIST_RADIUS join the fight against its target.
    Returns the helpers (empty if nobody came)."""
    if not getattr(npc, "pulled", False):
        return []
    npc.pulled = False
    target = npc.aggro_on
    if target is None or npc.prop or npc.merchant:
        return []
    faction = getattr(npc, "faction", None)
    helpers = []
    for other in npcs:
        if other is npc or not other.alive or other.aggro or other.prop or other.talks() \
                or getattr(other, "tombstone_of", None) or other.harvest or other.station:
            continue
        same = (faction is not None and getattr(other, "faction", None) == faction) or \
            (faction is None and other.template_id == npc.template_id)
        if same and math.hypot(other.location[0] - npc.location[0],
                               other.location[1] - npc.location[1]) <= ASSIST_RADIUS:
            helpers.append(other)
    for other in helpers:
        add_hate(other, target, 1)
        other.pulled = False
    return helpers


def taunt(npc, player):
    """Rescue/taunt: the player goes to the top of the NPC's hate list and becomes its target."""
    top = max((h for _p, h in npc.hate.values()), default=0.0)
    npc.hate[player.char_id] = [player, top * 1.2 + 10]
    npc.aggro, npc.aggro_on = True, player


def next_target(npc):
    """After its target died or left: the living player it hates most, or None."""
    alive = [(h, p) for p, h in npc.hate.values() if p.health > 0 and p is not npc.aggro_on]
    if not alive:
        return None
    return max(alive, key=lambda x: x[0])[1]


ARMOR_FACTOR = 100.0         # damage x 100 / (100 + armor class): 25 AC takes 20% off (placeholder curve)


def mitigate(dmg, armor_class):
    """Melee damage after the target's armor class (gear armor + Armor Class mods)."""
    if armor_class <= 0:
        return dmg
    return max(1, int(round(dmg * ARMOR_FACTOR / (ARMOR_FACTOR + armor_class))))


def player_avoidance(player):
    """The player's (dodge, parry, block) chances as npc_attacks rolls them (fractions)."""
    import zone
    gear = {e[3] for e in getattr(player, "equipment", [])}
    shield = any(zone.ITEM_CONTENT.item(e[1]).get("type") == "shield" for e in getattr(player, "equipment", []))
    dex = getattr(player, "stats", {}).get("dexterity", 30)
    return (BASE_DODGE + DODGE_PER_DEX * max(0, dex - 30), BASE_PARRY if gear & {28, 36} else 0.0,
            BASE_BLOCK if shield else 0.0)


# Character sheet avoidance: 0x11e MsgCombatInfo {f32 dodge, f32 parry, f32 block, f32, i32}
# (FUN_0055e020) fills AdvDexterityDodgeMax / AdvDexterityParryMax / AdvStrengthBlockMax with %.2f
# and shows each line only when it is above zero. Sent as percentages. The last two fields are
# kept at manager +0x80 / +0x84; their use is unknown, so 0.
COMBAT_INFO = 0x11E


def combat_info(player):
    dodge, parry, block = player_avoidance(player)
    return _event(COMBAT_INFO, struct.pack("<ffffi", dodge * 100, parry * 100, block * 100, 0.0, 0))


# Wounds (docs/EFFECTS.md "Wounds"): five body parts (head, torso, left arm, right arm, legs),
# each 0 Unwounded, 1 Minor, 2 Mid, 3 Major, 4 Incapacitated. An NPC's critical hit wounds a random
# part (WOUND_CHANCE); login_stub.wounds_tick sends the change and heals them while resting.
WOUND_PARTS = ("Head", "Torso", "Left Arm", "Right Arm", "Legs")
WOUND_MAX, WOUND_CHANCE = 4, 0.5


def wound(player, rng=random):
    if rng.random() >= WOUND_CHANCE:
        return
    w = list(getattr(player, "wounds", None) or [0] * 5)
    part = rng.randrange(5)
    if w[part] < WOUND_MAX:
        w[part] += 1
        player.wounds = w
        player.wounds_dirty = True


def npc_attacks(player, npc, rng=random):
    """The NPC strikes once. Lowers player.health (the HUD bar follows a
    0x2d4 update of the Health stat; see zone.health_update)."""
    if player.health <= 0:
        return []
    npc.aggro, npc.aggro_on = True, player
    gear = {e[3] for e in getattr(player, "equipment", [])}
    import zone
    shield = any(zone.ITEM_CONTENT.item(e[1]).get("type") == "shield" for e in getattr(player, "equipment", []))
    outcome = roll_outcome(rng, getattr(npc, "level", 1), getattr(player, "level_number", 1),
                           defender_dex=getattr(player, "stats", {}).get("dexterity", 30),
                           can_parry=bool(gear & {28, 36}), can_block=shield,
                           crit=getattr(npc, "crit", None))
    dmg = mitigate(rng.randint(*npc.damage), getattr(player, "armor_class", 0))
    if outcome == effects.CRIT:
        dmg = int(dmg * CRIT_MULT)
        wound(player, rng)
    elif outcome != effects.HIT:
        dmg = 0
    player.pending_displays.append(display_ability(npc.entity_id, player.char_id, npc.attack_visual))
    player.health = max(player.health - dmg, 0)
    player.pending_displays.append(effects.combat_text(npc.entity_id, player.char_id, "", dmg, kind=0,
                                                       dmg_type=HITS, outcome=outcome))
    lines = []
    if player.health == 0:
        lines.append(("You have been slain!", "error"))
    return lines


NPC_SPEED = 220.0            # units per second while chasing
FLEE_SPEED, FLEE_STEP = 0.8, 300.0   # a feared NPC runs at 80% speed away from its attacker
MELEE_RANGE = 90.0


STEER_ANGLES = (0, 30, -30, 60, -60, 90, -90, 120, -120)
LOOKAHEAD = 60.0             # extra distance checked ahead of a step


def steer(npc, ux, uy, step):
    """The direction to step in: (ux, uy) itself, or the nearest turn of it whose next
    step is clear of obstacles (npc.blocked); (None, None) when every way is blocked. An
    NPC already inside an obstacle's box (boxes are rough) may walk out of it."""
    if npc.blocked is None:
        return ux, uy
    x, y, z = npc.location
    if npc.blocked(x, y, z):
        return ux, uy
    for a in STEER_ANGLES:
        r = math.radians(a)
        vx, vy = ux * math.cos(r) - uy * math.sin(r), ux * math.sin(r) + uy * math.cos(r)
        d = step + LOOKAHEAD
        if not npc.blocked(x + vx * d, y + vy * d, z):
            return vx, vy
    return None, None


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
    ux, uy = steer(npc, dx / dist, dy / dist, step)
    if ux is None:                        # boxed in: stand still
        if not npc.moving:
            return None
        npc.moving = False
        return {"Velocity": (0.0, 0.0, 0.0), "PawnPosition": (npc.location, (0, npc.yaw, 0), (0.0, 0.0, 0.0))}
    yaw = int(math.degrees(math.atan2(uy, ux)) * 65536 / 360) & 0xFFFF
    z = npc.location[2]
    if npc.ground_z:
        z = npc.ground_z(npc.location[0] + ux * step, npc.location[1] + uy * step)
    npc.location = (npc.location[0] + ux * step, npc.location[1] + uy * step, z)
    npc.moving, npc.yaw = True, yaw
    vel = (ux * speed, uy * speed, 0.0)
    # PawnPosition also resets the client's ground-stick cache (see zone.py).
    return {"Location": npc.location, "Rotation": (0, yaw, 0), "Velocity": vel,
            "PawnPosition": (npc.location, (0, yaw, 0), vel)}


WANDER_SPEED = 90.0          # a stroll
WANDER_PAUSE = (4.0, 12.0)   # seconds standing between strolls
LEASH = 1500.0               # an NPC chasing further than this from home gives up


def give_up(npc):
    """Evade: leashed, or its last target died. It forgets who it was fighting, walks home and
    heals when it gets there (chase_step)."""
    npc.aggro, npc.aggro_on, npc.wander_goal = False, None, npc.home
    npc.hate.clear()
    npc.evading = True
    print(f"  {npc.name} gives up the chase and returns home")


def chase_step(npc, target, dt, rng=random, now=None):
    """One movement step for an NPC: chase its attacker (target = x, y, z), walk
    home after losing it, or wander around home within npc.wander. Returns the
    replicated properties to send, or None."""
    if not npc.alive:
        return None
    now = time.time() if now is None else now
    if now < getattr(npc, "feared_until", 0) and target is not None:
        # Feared: run straight away from its attacker (no leash check while it flees).
        dx, dy = npc.location[0] - target[0], npc.location[1] - target[1]
        d = math.hypot(dx, dy) or 1.0
        away = (npc.location[0] + dx / d * FLEE_STEP, npc.location[1] + dy / d * FLEE_STEP)
        return move_toward(npc, away, dt, NPC_SPEED * FLEE_SPEED, 1.0)
    if npc.aggro and target is not None:
        if math.hypot(npc.location[0] - npc.home[0], npc.location[1] - npc.home[1]) > LEASH:
            give_up(npc)
        else:
            return move_toward(npc, target, dt, NPC_SPEED, MELEE_RANGE)
    if npc.wander_goal is not None:
        values = move_toward(npc, npc.wander_goal, dt,
                             NPC_SPEED if npc.wander_goal == npc.home else WANDER_SPEED, 5.0)
        if not npc.moving:
            pause = npc.path_pause if npc.path else rng.uniform(*WANDER_PAUSE)
            npc.wander_goal, npc.next_wander = None, now + pause
            if getattr(npc, "evading", False):
                npc.evading = False
                npc.health = npc.max_health
                values = dict(values or {}, Health=npc.max_health)
                print(f"  {npc.name} is back home at full health")
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
ABILITY_COST = 15            # endurance (or energy) per ability use (placeholder)
# Spellcasting classes pay energy instead of endurance (races_classes ids): Cleric, Druid,
# Psionicist, Shaman, Sorcerer, Blood Mage, Necromancer.
ENERGY_CLASSES = {5, 7, 14, 22, 25, 44, 45}


NOT_ENOUGH_ENERGY, NOT_ENOUGH_ENDURANCE, NO_VALID_TARGET = 0x22, 0x24, 0x0B   # 0x241 codes


def pay_cost(player, refresh):
    """Spend an ability's cost: energy for casters, endurance for everyone else. Instant
    openers (no refresh) are free. Returns the client's failure code (0x241: 0x22 not enough
    energy, 0x24 not enough endurance), or None when paid."""
    cost = ABILITY_COST if refresh > 0 else 0
    if getattr(player, "klass", None) in ENERGY_CLASSES:
        energy = getattr(player, "energy", player.stats.get("energy", 100))
        if energy < cost:
            return NOT_ENOUGH_ENERGY
        player.energy = energy - cost
        if cost:
            player.energy_changed = True
        return None
    if player.endurance < cost:
        return NOT_ENOUGH_ENDURANCE
    player.endurance -= cost
    player.endurance_changed = True
    return None
ENDURANCE_REGEN = 4          # per second, in and out of combat


# Encounter ownership: 0x567 MsgTwoEntityIdsAndBool {eid64 npc, eid64 owner, bool8 damaged by an
# NPC} (FUN_00549da0). Every client records the owner; the owner's client prints VGClient.int
# YouHaveEstablishedOwnership ("You have established ownership."), or the group version when the
# owner id is its group's id; the bool picks the "...but the NPC has been significantly damaged by
# another NPC" wording.
OWNERSHIP = 0x567


def ownership(npc, owner, damaged_by_npc=False):
    return _event(OWNERSHIP, struct.pack("<QQB", npc.entity_id, owner, int(damaged_by_npc)))


def respawns(npcs, now):
    """NPCs (of one world) that come back to life now."""
    back = []
    for npc in npcs.values():
        if npc.died_at and now - npc.died_at >= npc.respawn:
            npc.health, npc.died_at = npc.max_health, None
            npc.aggro, npc.aggro_on, npc.moving = False, None, False
            npc.hate = {}
            npc.location, npc.loot, npc.wander_goal = npc.home, None, None
            npc.killer = npc.loot_owner = npc.coin_left = npc.casting = None
            npc.open_to_group, npc.pending, npc.rolled = False, set(), False
            npc.owner = None
            back.append(npc)
    return back


def tick(player, now):
    """Once a second for one player: auto-attack swings ('swing', lines, npc) and
    regeneration ('health',)."""
    out = []
    if player.auto_attack and now >= player.next_swing:
        player.next_swing = now + AUTO_ATTACK_SECONDS
        npc = player.npcs.get(player.target) if player.target else None
        opp = getattr(player, "duel_opponent", None)
        if opp is not None and player.target == opp.char_id and player.health > 0:
            out.append(("pvp", opp))
        elif npc is None or not npc.alive or player.health <= 0 or npc.service():
            player.auto_attack = False          # also when the target is now a vendor, station, pet...
            out.append(("swing", [], None))
        else:
            out.append(("swing", *strike(player, npc, "You", AUTO_ATTACK_VISUAL,
                                         *auto_attack_damage(player))))
    if player.health > 0 and player.endurance < player.stats["endurance"]:
        player.endurance = min(player.endurance + ENDURANCE_REGEN, player.stats["endurance"])
        out.append(("endurance",))
    if 0 < player.health < player.stats["hit_points"] and now - player.last_combat >= REGEN_DELAY:
        regen = REGEN_PER_SECOND * (3 if getattr(player, "resting", False) else 1)
        regen += round(getattr(player, "regen_bonus", 0) / 6.0)   # Health Regeneration mods are "per 6 seconds"
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


# Loot sparkle (FUN_005249b0): 0x564 {eid64} starts the sparkle effect on a corpse that has
# something to loot, once per entity (FUN_00524920); 0x565 {eid64} stops it (FUN_00523f20).
LOOT_SPARKLE_EVENT = 0x564
LOOT_SPARKLE_OFF_EVENT = 0x565


def loot_sparkle(npc, on=True):
    return _event(LOOT_SPARKLE_EVENT if on else LOOT_SPARKLE_OFF_EVENT, struct.pack("<Q", npc.entity_id))


def corpse_coin(npc, rng=random):
    """Copper on a corpse: mobs.json "coin" [min, max], else 2-6 copper per level. Rolled
    once per death."""
    if npc.coin_left is None:
        lo, hi = npc.coin if npc.coin else (2 * npc.level, 6 * npc.level)
        npc.coin_left = rng.randint(int(lo), int(hi))
    return npc.coin_left


def take_loot(player, npc, handle):
    """Move loot items (handle -1 = all) into the player's bag. Returns messages."""
    import vgmsg
    out = []
    pending = getattr(npc, "pending", set())      # items in a group loot roll
    for item in [i for i in (npc.loot or []) if handle in (-1, i[0]) and i[0] not in pending]:
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


KOS_AGGRO_RADIUS = 1000.0       # NPCs attack players their faction holds Kill on Sight


def proximity_aggro(npc, players, kos=None):
    """An aggressive NPC picks the nearest living player inside its aggro radius
    (or KOS_AGGRO_RADIUS for players kos(p) says its faction hates).
    Returns that player when it starts a fight, else None."""
    if npc.aggro or not npc.alive or npc.merchant or npc.harvest or getattr(npc, "prop", False):
        return None
    if getattr(npc, "fighting_pet_until", 0) > time.time():
        return None                                  # busy with a player's pet
    home = getattr(npc, "home", None)
    if home is not None and math.hypot(npc.location[0] - home[0], npc.location[1] - home[1]) > LEASH:
        return None      # leashed and walking home: re-aggroing here would drop again next tick
    best = None
    for p in players:
        pos = p.live_position or p.spawned_at
        if pos is None or p.health <= 0:
            continue
        radius = max(npc.aggro_radius, KOS_AGGRO_RADIUS if kos and kos(p) else 0)
        if radius <= 0:
            continue
        d = math.hypot(pos[0] - npc.location[0], pos[1] - npc.location[1])
        if d <= radius and (best is None or d < best[0]):
            best = (d, p)
    if best:
        add_hate(npc, best[1], 1)
        return best[1]
    return None
