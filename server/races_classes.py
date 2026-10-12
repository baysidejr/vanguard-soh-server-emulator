"""Race and class ids as the client uses them (names from the client's own
tables: races FUN_00d02540, classes FUN_00d07120). The character-create request
stores the race at +7 and the adventuring class at +8 (login_stub.character_race_class)."""

# The 19 playable races (ids 0 Cat Person, 1 Deep Dwarf, 0x13 Kojan Barbarian and
# 0x10, a second id for Orc, also exist in the client table).
RACES = {
    0x02: "Dwarf", 0x03: "Dark Elf", 0x04: "High Elf", 0x05: "Wood Elf", 0x06: "Gnome",
    0x07: "Goblin", 0x08: "Half Elf", 0x09: "Lesser Giant", 0x0A: "Halfling",
    0x0B: "Orc", 0x0C: "Kojani", 0x0D: "Qaliathari", 0x0E: "Thestran",
    0x0F: "Mordebi", 0x11: "Raki", 0x12: "Vulmane", 0x14: "Varanthari",
    0x15: "Varanjar", 0x16: "Kurashasa",
}

# The 15 adventuring classes.
ADVENTURING_CLASSES = {
    0x02: "Bard", 0x04: "Paladin", 0x05: "Cleric", 0x07: "Druid", 0x0E: "Psionicist",
    0x0F: "Monk", 0x13: "Ranger", 0x14: "Dread Knight", 0x15: "Rogue", 0x16: "Shaman",
    0x19: "Sorcerer", 0x1B: "Disciple", 0x1C: "Warrior", 0x2C: "Blood Mage",
    0x2D: "Necromancer",
}

# Other class ids in the same table: crafting, harvesting and diplomacy.
OTHER_CLASSES = {
    0x01: "Adventurer", 0x08: "Harvester", 0x1D: "Foreman", 0x1E: "Reaper",
    0x1F: "Prospector", 0x20: "Gleaner", 0x23: "Philosopher", 0x24: "Demagogue",
    0x25: "Thug", 0x26: "Charlatan", 0x30: "Diplomat",
}


def race_name(race_id):
    return RACES.get(race_id, f"race {race_id:#x}")


def class_name(class_id):
    return ADVENTURING_CLASSES.get(class_id) or OTHER_CLASSES.get(class_id, f"class {class_id:#x}")
