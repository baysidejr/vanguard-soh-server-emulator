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
