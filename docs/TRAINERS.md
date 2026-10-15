# Ability trainers

**Verified live (2026-10-12):** Veyla Brightsteel (Combat Trainer, `"trainer": true` in mobs.json) offers "Do you have anything to teach me?". The Ability Training window lists the next six Warrior abilities, each costing 1 silver more than the one before. Train charges the coins, adds the ability to the book (`0x215`) and prints "You have learned Taunting Strike I.". Learned abilities are saved per character (`learned_abilities`) and come back at login. The code is in `server/trainer.py` and `login_stub.handle_trainer_event`.

The client's trainer dispatcher is `FUN_005d0d40`. All messages are zone events.

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| S→C | `0x2b1` | none | adds the "teach" dialogue option (type 0) |
| C→S | `0x168` | none | option clicked: begin training (`FUN_005ce010`) |
| S→C | `0x492` | none | training started (gamevar `Training` = 1, the dialogue closes) |
| S→C | `0x493` | `i32 n`, n × `{wstr name, wstr description, i32 ability id, i32 icon, f32 cost copper}` | trainable list; **appends** to the client's list |
| S→C | `0x494` | same as `0x493` | a second list shown after the first (probably "not yet trainable"; unused) |
| C→S | `0x16a` | `i32 ability id` | Train button (or `/train <name>`) |
| S→C | `0x495` | `i32 ability id, u8 result` | 0 ok (the entry is dropped), 1 not training, 2 not available, 3 can't afford, 5 inventory locked, 6 too powerful, 0xff failed |
| C→S | `0x169` | none | Done |
| S→C | `0x496` | `u8 reason` | training ended, both lists freed (5 prints "Training ended.") |

The trainer messages never touch the ability book. The server adds the ability with `0x215`, charges with `0x1aa`, and prints its own line.

Abilities come from the class's `<PREFIX>_ABILITIES.aby` (rank I tags, `class_abilities.py`). Real levels and costs were server data; the emulator uses the package order and placeholder prices (see CONTENT_EDITOR.md).

# Recipe trainers

**Verified live (2026-10-13):** Brenna Ashford (Smelting Trainer, `"recipe_trainer": ["copper_wire"]` in mobs.json) shows the client's own option "I'd like to learn recipes from you.". The Recipe Training window lists Copper Wire (icon, description, 50 copper). Train prints "You lose 50 copper." and "You have learned the recipe Copper Wire.", and the recipe appears under Normal Recipes at the forge. Learned recipes are saved per character (`known_recipes`); recipes with a `trainer_cost` are not in the book until learned.

Client dispatcher `FUN_005af590`. The flow mirrors ability trainers:

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| S→C | `0x2b2` | none | adds the dialogue option (type 1, text "I'd like to learn recipes from you." from the client, `FUN_004c7a00`) |
| C→S | `0x16b` | none | option clicked: begin (`FUN_005ac900`) |
| S→C | `0x497` | none | training started ("You begin to train.", gamevar `RecipeTraining`) |
| S→C | `0x498` | `{wstr name, wstr description, i32 recipe id, i32 icon, f32 cost copper}` | **one** recipe, appended (no count prefix; `FUN_005af140`) |
| C→S | `0x16d` | `i32 recipe id` | Train |
| S→C | `0x499` | `i32 recipe id, u8 result` | codes as `0x495` |
| C→S | `0x16c` | none | Done (`FUN_005ac930`) |
| S→C | `0x49a` | `u8 reason` | ended (codes as `0x496`; 2 = "Your target has nothing to teach you right now.") |

Recipe trainers have `EntityTypes 0x80`. The other built-in dialogue options added by `0x2b1`–`0x2ba` (`FUN_004c7a00`, option type in brackets): 0x2b1 "Do you have anything to teach me?" [0], 0x2b2 recipes [1], 0x2b3 "I need to do some banking" [3], 0x2b4 "I'm looking for work." [4].

Assembly trainers (`0x49c`–`0x4a0`, `MsgAssemblyTrainerRecipe {wstr, i32, i32, f32, wstr}`) follow the same pattern; they are implemented and partly verified live in docs/ASSEMBLY.md (Brenna Ashford, Copper Ring).
