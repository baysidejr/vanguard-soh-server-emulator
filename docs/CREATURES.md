# Creature spawning: race table, meshes, model variants

> **Verified live (2026-10-12):** SGONPCPawn with `m_iRaceId` 119 (wolf, `m_iModelNum` 1) and 69 (bear) render as real creatures with name plates and minimap entries; mob templates set `race`/`model`/`gender` in `server/content/mobs.json`.


Source: VGClient.exe (Ghidra/REA static analysis) + Assets/Characters/Meshes/UEM_*_char.uem name tables.

## 1. Where the race table comes from

The race table is **hard-coded in VGClient.exe**. No data file is involved (cust_race_mods_v2.txt only holds player customization).

- `FUN_00bf26b0` is the race-table init. It runs on the global object `DAT_01924754`, which holds the race pointer array at `+0xe4200`.
  It loops over ids 0..0x7d1 and mallocs a 0x110-byte entry (via ctor `FUN_00bf22a0(id, type)`) for these ranges:
  - ids 2..0x16: type 0, `+0x30 = "PCPackage"`. These are the player races.
  - ids 0x40..0x17e and 2001: type 1, `+0x30 = "NPCPackage"`. These are creatures and NPC races.
  - ids 0x20f..0x36e and 0x3e9..0x44f: type 2. These are static-mesh "races" (mailboxes, props, ...).
  - All other ids get a NULL pointer, so they fall back to race 0x5d (93, Mouseman).
- It then calls the per-range fillers:
  - `FUN_00bd6060` fills the playable races 2..22.
  - `FUN_00be2760` fills **all creatures and NPC races 64..382**. Each block is `FString name = "Wolf"; entry->+0x20 = L"wolf"; ...`.
  - `FUN_00bd7650` fills the type-2 static-mesh props (527..878, 1001..1103).
  - `FUN_00bd14e0` and `FUN_00bd3020` fill the anim-name and FX-name tables (not races).
- Validity check used by the pawn code: `entry != NULL && entry->+0x18 (FString name length) != 0`. Otherwise the client uses `+0xe4374` (race 93 "Mouseman").
  Unnamed ids in 64..382 are 129 and 135..141. They render as mouseman.

### Race entry layout (0x110 bytes; [g] = gender 0/1)
| off | meaning |
|---|---|
| +0x04 | FString race name (len at +0x18 = validity) |
| +0x20 / +0x24 | mesh base name, male / female (wchar*) |
| +0x30 | package kind "PCPackage" / "NPCPackage" |
| +0x34 / +0x38 | item/attachment set name (e.g. GNOLL, ZOMBIE_M) -> *_ITEMS.uem |
| +0x48 / +0x4c | sound package M/F |
| +0x68 / +0x6c | collision height M/F (default 90) |
| +0x70 / +0x74 | collision radius M/F (default 30) |
| +0x88 / +0x8c | mesh scale M/F (default 1.0) |
| +0xa8 / +0xac | copied to pawn[0xc0] |
| +0xb0 / +0xb4 | **default model number M/F (used when m_iModelNum < 0; default 0)** |
| +0xe8 / +0xec | anim/movement ints copied to the EMFX instance |
| +0xf1 | allows attachments 0x15..0x2b when set (cleared for most creatures) |

## 2. How the mesh is built (`FUN_00bcb8e0` -> `FUN_00bc2e90`)

1. `race = m_iRaceId` (if >= 0x7d2 the client forces 0x5d). The entry is looked up as above.
2. `g = gender (vfunc 0x2b0)`. If g > 1 it becomes 0. `mesh = entry[+0x20 + g*4]`. If that is empty: female falls back to the male mesh, and male falls back to "mouseman".
3. `model = (m_iModelNum < 0) ? entry[+0xb0 + g*4] : m_iModelNum`.
4. For races 2..22 and 64..382 (`FUN_00d07d00` / `FUN_00d07d10`), it loads the EMFX object:
   `UEM_<mesh>_<M|F>_char.<mesh>_<M|F>_char_ALL_<model>_SKELETON`
   Fallback order:
   1. `_ALL_<model>_` with the pawn's gender letter.
   2. `_ALL_0_`.
   3. If male: the same two names with the `F` letter, then a plain skeletal mesh by name.
   4. If female: a plain skeletal mesh by name.

   `BassMesh` and `GarMesh` are loaded as UE skeletal meshes instead.
5. **m_iModelNum = the N in `_ALL_N_SKELETON`.** It selects a texture/geometry variant inside the same UEM package (e.g. wolf 0..3, bear 0,1,10,11). If N does not exist, the client falls back to 0. The variant lists below were read from each package's name table.
6. Afterwards `FUN_00bc95a0` / `FUN_00bc8cb0` apply the mesh scale (+0x88) and **set the collision cylinder from +0x68/+0x70 × DrawScale**. So the server does not need to send collision or scale. Leave DrawScale at 1.0 (it is a multiplier).

## 3. What the server needs to send for a creature
- `m_iRaceId` = id from the table below. This is all that is required.
- `m_iModelNum` = -1 (race default, usually 0) or a variant number from the list.
- Gender: 0 (male) for all creatures except the female-only meshes: Yukionna 109, Gorgon 223, Dryad 171, Siren 271, Vampire 277, Corpse 281, SeaHag 286, Banshee 333. Those **must** have gender = 1 (female), otherwise they render as mouseman.
  SpiderGiant/BlackWidow (104/155) have only an `_F_` package, but the male path falls back to F automatically.
- No attachment groups, collision or DrawScale are needed. For races 64..382 the code skips most attachment slots (it only allows slot ids 100/500/501/601, and 0x15..0x2b when +0xf1 is set).
- Ids 2..22 are player races (PCPackage, customizable). 186..207 are NPC versions of the player races (npcHuman etc., large variant lists). 348..368 are "optimized" player-race meshes.

## 4. Full race table (from FUN_00bd6060 + FUN_00be2760)
Columns: id (dec/hex) | race name | male mesh | female mesh | package + available model variants | scale | coll H/R | default model | sounds

| id | hex | name | M mesh | F mesh | package [variants] | scale | H/R | defModel | sounds |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 0x2 | Dwarf | dwarf | dwarf | UEM_dwarf_M_char [0] / UEM_dwarf_F_char [0] | 1.11 | 75.0/22.5 |  |  |
| 3 | 0x3 | DarkElf | elf | elf | UEM_elf_M_char [0, 1, 2] / UEM_elf_F_char [0, 1, 2] | 1.056 | 90.0/27.0 | 1 |  |
| 4 | 0x4 | HighElf | elf | elf | UEM_elf_M_char [0, 1, 2] / UEM_elf_F_char [0, 1, 2] | 1.056 | 90.0/27.0 |  |  |
| 5 | 0x5 | WoodElf | elf | elf | UEM_elf_M_char [0, 1, 2] / UEM_elf_F_char [0, 1, 2] | 1.056 | 90.0/27.0 | 2 |  |
| 6 | 0x6 | Gnome | gnome | gnome | UEM_gnome_M_char [0] / UEM_gnome_F_char [0] | 0.8 | 60.0/18.0 |  |  |
| 7 | 0x7 | Goblin | goblin | goblin | UEM_goblin_M_char [0] / UEM_goblin_F_char [0] | 0.833 | 75.0/22.5 |  |  |
| 8 | 0x8 | HalfElf | halfElf | halfElf | UEM_halfElf_M_char [0] / UEM_halfElf_F_char [0] | 1.0 | 90.0/27.0 |  |  |
| 9 | 0x9 | LesserGiant | halfGiant | halfGiant | UEM_halfGiant_M_char [0] / UEM_halfGiant_F_char [0] | 1.238 | 105.0/31.5 |  |  |
| 10 | 0xA | Halfling | halfling | halfling | UEM_halfling_M_char [0] / UEM_halfling_F_char [0] | 0.658 | 60.0/18.0 |  |  |
| 11 | 0xB | HalfOrc | halfOrc | halfOrc | (no M; MISSING) / (no F; MISSING) | 1.0 | 90.0/27.0 |  |  |
| 12 | 0xC | Kojani | human | human | UEM_human_M_char [0, 1, 2, 3] / UEM_human_F_char [0, 1, 2, 3] | 1.0 | 90.0/27.0 | 2 |  |
| 13 | 0xD | Qaliathari | human | human | UEM_human_M_char [0, 1, 2, 3] / UEM_human_F_char [0, 1, 2, 3] | 1.0 | 90.0/27.0 | 3 |  |
| 14 | 0xE | Thestran | human | human | UEM_human_M_char [0, 1, 2, 3] / UEM_human_F_char [0, 1, 2, 3] | 1.0 | 90.0/27.0 |  |  |
| 15 | 0xF | Mordebi | human | human | UEM_human_M_char [0, 1, 2, 3] / UEM_human_F_char [0, 1, 2, 3] | 1.0 | 90.0/27.0 | 1 |  |
| 16 | 0x10 | Orc | orc | orc | UEM_orc_M_char [0] / UEM_orc_F_char [0] | 1.005 | 90.4/27.1 |  |  |
| 17 | 0x11 | Raki | raki | raki | UEM_raki_M_char [0] / UEM_raki_F_char [0] | 0.85 | 60.0/18.0 |  |  |
| 18 | 0x12 | Vulmane | vulmane | vulmane | UEM_vulmane_M_char [0, 1] / UEM_vulmane_F_char [0, 1] | 1.136 | 97.5/29.25 |  |  |
| 19 | 0x13 | KojanBarbarian | kojanBarbarian | kojanBarbarian | (no M; MISSING) / (no F; MISSING) | 1.0 | 90.0/27.0 |  |  |
| 20 | 0x14 | Varanthari | barbarian | barbarian | UEM_barbarian_M_char [0, 1, 2] / UEM_barbarian_F_char [0, 1] | 1.088 | 97.5/29.25 | 1 |  |
| 21 | 0x15 | Varanjar | barbarian | barbarian | UEM_barbarian_M_char [0, 1, 2] / UEM_barbarian_F_char [0, 1] | 1.088 | 97.5/29.25 |  |  |
| 22 | 0x16 | Kurashasa | kura | kura | UEM_kura_M_char [0] / UEM_kura_F_char [0] | 1.151 | 97.5/29.25 |  |  |
| 64 | 0x40 | Ratman | ratman |  | UEM_ratman_M_char [0] | 1.0 | 70.0/40.0 |  | RatmanSounds |
| 65 | 0x41 | AntGiant | ant |  | UEM_ant_M_char [0, 1, 2, 3, 4, 5, 10, 100, 101] | 1.0 | 50.0/90.0 |  | GiantAntSounds |
| 66 | 0x42 | Badger | badger |  | UEM_badger_M_char [0, 1] | 1.0 | 40.0/40.0 |  | BadgerSounds |
| 67 | 0x43 | Rat | rat |  | UEM_rat_M_char [0, 1] | 1.0 | 40.0/40.0 |  | RatSounds |
| 68 | 0x44 | Basilisk | basilisk |  | UEM_basilisk_M_char [0] | 1.0 | 50.0/60.0 |  | BasiliskSounds |
| 69 | 0x45 | Bear | bear |  | UEM_bear_M_char [0, 1, 10, 11] | 1.0 | 70.0/50.0 |  | BearSounds |
| 70 | 0x46 | BoarWild | boar |  | UEM_boar_M_char [0, 1, 100, 101] | 1.0 | 100.0/60.0 |  | WildBoarSounds |
| 71 | 0x47 | CarrionCrawler | carrionCrawler |  | UEM_carrionCrawler_M_char [0] | 1.0 | 80.0/80.0 |  | CarrionCrawlerSounds |
| 72 | 0x48 | Chiranha | chiranha |  | UEM_chiranha_M_char [0] | 1.0 | 50.0/40.0 |  | ChiranaSounds |
| 73 | 0x49 | Cockatrice | cockatrice |  | UEM_cockatrice_M_char [0, 1] | 1.0 | 75.0/45.0 |  | CockatriceSounds |
| 74 | 0x4A | Cockroach | cockroach |  | UEM_cockroach_M_char [0] | 1.0 | 50.0/80.0 |  | CockroachSounds |
| 75 | 0x4B | Drake | drake |  | UEM_drake_M_char [0, 10] | 2.0 | 130.0/50.0 |  | DrakeSounds |
| 76 | 0x4C | Ettercap | ettercap |  | UEM_ettercap_M_char [0, 1] | 1.0 | 72.0/80.0 |  | EttercapSounds |
| 77 | 0x4D | Gremlin | gremlin |  | UEM_gremlin_M_char [0, 1, 2, 10, 11, 12, 20, 21, 22] | 1.0 | 70.0/40.0 |  | GremlinSounds |
| 78 | 0x4E | ClayWarrior | clayWarrior |  | UEM_clayWarrior_M_char [0] | 1.0 | 90.0/30.0 |  | ClayWarriorSounds |
| 79 | 0x4F | DuneCrawler | duneCrawler |  | UEM_duneCrawler_M_char [0] | 1.0 | 80.0/80.0 |  | DuneCrawlerSounds |
| 80 | 0x50 | Gnoll | gnoll |  | UEM_gnoll_M_char [0] | 1.0 | 115.0/50.0 |  | GnollSounds |
| 81 | 0x51 | Behemoth | behemoth |  | UEM_behemoth_M_char [0, 1] | 1.0 | 75.0/40.0 |  | BehemothSounds |
| 82 | 0x52 | Rhinoceros | rhinoceros |  | UEM_rhinoceros_M_char [0, 1, 2, 3, 4, 5] | 1.0 | 75.0/40.0 |  | RhinoSounds |
| 83 | 0x53 | Griffon | griffon |  | UEM_griffon_M_char [0, 10, 20, 30, 40] | 2.0 | 150.0/50.0 |  | GriffonSounds |
| 84 | 0x54 | Mosquito | mosquito |  | UEM_mosquito_M_char [0] | 1.0 | 90.0/30.0 |  | MosquitoSounds |
| 85 | 0x55 | Hobgoblin | hobgoblin |  | UEM_hobgoblin_M_char [0, 10, 20] | 1.502 | 135.0/45.0 |  | HobgoblinSounds |
| 86 | 0x56 | Jharuu | jharuu |  | UEM_jharuu_M_char [0] | 1.0 | 104.0/60.0 |  | JharuuSounds |
| 87 | 0x57 | Kobold | kobold |  | UEM_kobold_M_char [0] | 1.0 | 70.0/40.0 |  | KoboldSounds |
| 88 | 0x58 | Djinn | djinn |  | UEM_djinn_M_char [0, 1] | 1.0 | 85.0/30.0 |  | DjinnSounds |
| 89 | 0x59 | WingedEye | wingedEye |  | UEM_wingedEye_M_char [0] | 1.0 | 200.0/75.0 |  | WingedEyeSounds |
| 90 | 0x5A | Lich | lich | lich | UEM_lich_M_char [0, 10, 20] / UEM_lich_F_char [0, 10] | 1.0 | 90.0/30.0 |  | LichMaleSounds |
| 91 | 0x5B | Vinewalker | Vinewalker |  | UEM_Vinewalker_M_char [0, 1] | 1.0 | 50.0/90.0 |  | VineWalkerSounds |
| 92 | 0x5C | Pangolin | pangolin |  | UEM_pangolin_M_char [0, 10] | 1.0 | 40.0/40.0 |  | PangolinSounds |
| 93 | 0x5D | Mouseman | mouseman |  | UEM_mouseman_M_char [0] | 1.0 | 90.0/30.0 |  |  |
| 94 | 0x5E | Wyvern | wyvern |  | UEM_wyvern_M_char [0, 10, 20] | 2.0 | 130.0/50.0 |  | WyvernSounds |
| 95 | 0x5F | RiftWalker | chupacabra |  | UEM_chupacabra_M_char [0, 10] | 1.0 | 200.0/55.0 |  | RiftWalkerSounds |
| 96 | 0x60 | Ooze | ooze |  | UEM_ooze_M_char [0] | 1.0 | 75.0/150.0 |  | OozeSounds |
| 97 | 0x61 | Ram | ram |  | UEM_ram_M_char [0] | 1.0 | 100.0/40.0 |  | RamSounds |
| 98 | 0x62 | Yeti | yeti |  | UEM_yeti_M_char [0] | 1.0 | 90.0/30.0 |  | YetiSounds |
| 99 | 0x63 | Salamander | salamander |  | UEM_salamander_M_char [0, 10, 20, 21, 30, 31, 32, 40, 50, 51, 60, 70, 80, 81] | 1.0 | 120.0/45.0 |  | SalamanderSounds |
| 100 | 0x64 | ShamblingMound | shamblingMound |  | UEM_shamblingMound_M_char [0, 2, 10, 20] | 1.0 | 120.0/60.0 |  | ShamblingMoundSounds |
| 101 | 0x65 | Skeleton | skeleton | skeleton | UEM_skeleton_M_char [0, 1, 2, 3, 10, 13, 23] / UEM_skeleton_F_char [0, 10] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 102 | 0x66 | Snake | snake |  | UEM_snake_M_char [0, 1] | 1.0 | 20.0/40.0 |  | SnakeSounds |
| 103 | 0x67 | Coralwalker | coralwalker |  | UEM_coralwalker_M_char [0] | 1.0 | 50.0/90.0 |  | CoralWalkerSounds |
| 104 | 0x68 | SpiderGiant | spiderBlackWidow | spiderBlackWidow | (no M; falls back to spiderblackwidow_f_char [0, 1, 2, 3, 100, 101]) / UEM_spiderBlackWidow_F_char [0, 1, 2, 3, 100, 101] | 1.0 | 75.0/90.0 |  | GiantSpiderSounds |
| 105 | 0x69 | Sandrunner | sandrunner |  | UEM_sandrunner_M_char [0] | 1.0 | 75.0/45.0 |  | SwordbeakSounds |
| 106 | 0x6A | Stirge | stirge |  | UEM_stirge_M_char [0] | 2.0 | 141.0/25.0 |  | StirgSounds |
| 107 | 0x6B | SwampBrute | swampBrute |  | UEM_swampBrute_M_char [0, 1] | 1.0 | 150.0/100.0 |  | SwampBruteSounds |
| 108 | 0x6C | Swordbeak | Swordbeak |  | UEM_Swordbeak_M_char [0, 1] | 1.0 | 75.0/45.0 |  | SwordbeakSounds |
| 109 | 0x6D | Yukionna |  | yukionna | UEM_yukionna_F_char [0] | 1.0 | 90.0/30.0 |  |  |
| 110 | 0x6E | Toad | toad |  | UEM_toad_M_char [0] | 1.0 | 70.0/80.0 |  | ToadSounds |
| 111 | 0x6F | Treant | treant |  | UEM_treant_M_char [0, 1, 2, 3] | 1.0 | 300.0/100.0 |  | TreantSounds |
| 112 | 0x70 | Troglodyte | troglodyte |  | UEM_troglodyte_M_char [0] | 1.0 | 80.0/40.0 |  | TroglodyteSounds |
| 113 | 0x71 | Troll | troll |  | UEM_troll_M_char [0, 1] | 1.0 | 146.0/60.0 |  | TrollSounds |
| 114 | 0x72 | Turtle | turtle |  | UEM_turtle_M_char [0] | 1.0 | 50.0/100.0 |  | TurtleSounds |
| 115 | 0x73 | Ulvari | oni |  | UEM_oni_M_char [0, 1, 11] | 1.0 | 95.0/35.0 |  | UlvariSounds |
| 116 | 0x74 | UlvariMinor | oni_Minor |  | UEM_oni_Minor_M_char [0, 1, 11] | 1.0 | 90.0/30.0 |  | UlvariMinorSounds |
| 117 | 0x75 | Wight | wight |  | UEM_wight_M_char [0] | 1.0 | 90.0/30.0 |  | GhoulSounds |
| 118 | 0x76 | Willowisp | willowisp |  | UEM_willowisp_M_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 90, 91, 92, 93, 94] | 1.0 | 100.0/30.0 |  | WillowispSounds |
| 119 | 0x77 | Wolf | wolf |  | UEM_wolf_M_char [0, 1, 2, 3] | 1.0 | 40.0/25.0 |  | WolfSounds |
| 120 | 0x78 | Wolverine | wolverine |  | UEM_wolverine_M_char [0] | 1.0 | 40.0/30.0 |  | WolverineSounds |
| 121 | 0x79 | WormGiant | worm |  | UEM_worm_M_char [0] | 1.0 | 100.0/40.0 |  | GiantWormSounds |
| 122 | 0x7A | Wraith | wraith | wraith | UEM_wraith_M_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] / UEM_wraith_F_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 123 | 0x7B | TreeTangleleaf | treeTangleleaf |  | UEM_treeTangleleaf_M_char [0] | 1.0 | 1200.0/50.0 |  |  |
| 124 | 0x7C | Zombie | zombie | zombie | UEM_zombie_M_char [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 20, 21] / UEM_zombie_F_char [0, 1, 12] | 1.0 | 90.0/30.0 |  | ZombieMaleSounds |
| 125 | 0x7D | Ghoul | ghoul |  | UEM_ghoul_M_char [0, 1, 10] | 1.0 | 90.0/30.0 |  | GhoulSounds |
| 126 | 0x7E | MoleShark | moleShark |  | UEM_moleShark_M_char [0, 1] | 1.0 | 60.0/60.0 |  | MoleSharkSounds |
| 127 | 0x7F | Chicken | chicken |  | UEM_chicken_M_char [0] | 1.0 | 23.0/15.0 |  | ChickenSounds |
| 128 | 0x80 | Sheep | sheep |  | UEM_sheep_M_char [0] | 1.0 | 60.0/50.0 |  | SheepSounds |
| 130 | 0x82 | SpiderWolf | spiderWolf |  | UEM_spiderWolf_M_char [0, 1] | 1.0 | 70.0/150.0 |  | SpiderWolfSounds |
| 131 | 0x83 | Gar | GarMesh |  | SkeletalMeshes ukx (Bass/Gar special case) | 1.0 | 8.0/10.0 |  | GarSounds |
| 132 | 0x84 | Bass | BassMesh |  | SkeletalMeshes ukx (Bass/Gar special case) | 1.0 | 10.0/10.0 |  | BassSounds |
| 133 | 0x85 | BasiliskSavannah | basiliskSavannah |  | UEM_basiliskSavannah_M_char [0] | 1.0 | 100.0/225.0 |  | BasiliskSavannahSounds |
| 134 | 0x86 | Scorpion | scorpion |  | UEM_scorpion_M_char [0, 1] | 1.0 | 40.0/45.0 |  | ScorpionSounds |
| 142 | 0x8E | TreePalm | treePalm |  | UEM_treePalm_M_char [0, 1] | 1.0 | 350.0/40.0 | 1 |  |
| 143 | 0x8F | TreeVine | treeVine |  | UEM_treeVine_M_char [0, 1] | 1.0 | 375.0/40.0 | 1 |  |
| 144 | 0x90 | TreeAmada | treeOak |  | UEM_treeOak_M_char [0, 1] | 1.0 | 1000.0/100.0 |  |  |
| 145 | 0x91 | Bugbear | bugbear | bugbear | UEM_bugbear_M_char [0] / UEM_bugbear_F_char [0] | 1.0 | 85.0/35.0 |  | BugBearMaleSounds |
| 146 | 0x92 | Crab | crab |  | UEM_crab_M_char [0, 1] | 1.0 | 150.0/450.0 |  | CrabSounds |
| 147 | 0x93 | Wasp | wasp |  | UEM_wasp_M_char [0] | 1.0 | 75.0/50.0 |  | WaspSounds |
| 148 | 0x94 | SoulSlasher | soulSlasher |  | UEM_soulSlasher_M_char [0, 10] | 1.0 | 55.0/100.0 |  | SoulSlasherSounds |
| 149 | 0x95 | SwamphibianBaby | swamphibianBaby |  | UEM_swamphibianBaby_M_char [0] | 1.0 | 75.0/90.0 |  | SwamphibianBabySounds |
| 150 | 0x96 | SwamphibianBoss | swamphibianBoss |  | UEM_swamphibianBoss_M_char [0, 1, 2] | 1.0 | 136.0/150.0 |  | SwamphibianBossSounds |
| 151 | 0x97 | SwamphibianFlyer | swamphibianFlyer |  | UEM_swamphibianFlyer_M_char [0, 10, 20] | 1.0 | 400.0/325.0 |  | SwamphibianFlyerSounds |
| 152 | 0x98 | Manphibian | manphibian |  | UEM_manphibian_M_char [0, 1] | 1.0 | 68.0/35.0 |  | ManphibianSounds |
| 153 | 0x99 | Fairy | fairy | fairy | (no M; falls back to fairy_f_char [0, 1, 2, 3, 4, 10, 11, 12]) / UEM_fairy_F_char [0, 1, 2, 3, 4, 10, 11, 12] | 0.5 | 85.0/25.0 |  | FairySounds |
| 154 | 0x9A | Mantodea | mantodea |  | UEM_mantodea_M_char [0] | 1.0 | 150.0/75.0 |  | MantodeaSounds |
| 155 | 0x9B | SpiderBlackWidow | spiderBlackWidow | spiderBlackWidow | (no M; falls back to spiderblackwidow_f_char [0, 1, 2, 3, 100, 101]) / UEM_spiderBlackWidow_F_char [0, 1, 2, 3, 100, 101] | 1.0 | 75.0/90.0 |  | GiantSpiderSounds |
| 156 | 0x9C | Scarab | scarab |  | UEM_scarab_M_char [0, 1, 2, 3, 4, 5] | 1.0 | 100.0/50.0 |  | ScarabSounds |
| 157 | 0x9D | ThestranTree1 | thestranTree1 |  | UEM_thestranTree1_M_char [0] | 1.0 | 480.0/60.0 |  |  |
| 158 | 0x9E | Manticore | manticore |  | UEM_manticore_M_char [0, 10, 20] | 1.0 | 100.0/100.0 |  | ManticoreSounds |
| 159 | 0x9F | ForgeQalia | forgeQalian |  | UEM_forgeQalian_M_char [0] | 1.0 | 120.0/150.0 |  |  |
| 160 | 0xA0 | SmelterQalia | smelterQalian |  | UEM_smelterQalian_M_char [0] | 1.0 | 135.0/150.0 |  |  |
| 161 | 0xA1 | HorseDraft | horseDraft |  | (no M; MISSING) | 1.2 | 110.0/50.0 |  | QuarterHorseSounds |
| 162 | 0xA2 | UndeadConstruct | undeadConstruct |  | UEM_undeadConstruct_M_char [0] | 1.0 | 100.0/60.0 |  | UndeadConstructSounds |
| 163 | 0xA3 | Bat | bat |  | UEM_bat_M_char [0] | 1.0 | 225.0/50.0 |  | BatSounds |
| 164 | 0xA4 | Ogre | ogre |  | UEM_ogre_M_char [0] | 1.5 | 150.0/50.0 |  | OgreSounds |
| 165 | 0xA5 | Dragonfly | dragonfly |  | UEM_dragonfly_M_char [0] | 1.0 | 75.0/50.0 |  | DragonflySounds |
| 166 | 0xA6 | Moth | moth |  | UEM_moth_M_char [0] | 1.0 | 75.0/50.0 |  | MothSounds |
| 167 | 0xA7 | Crocodile | crocodile |  | UEM_crocodile_M_char [0, 1, 2] | 1.0 | 30.0/50.0 |  | CrocodileSounds |
| 168 | 0xA8 | KomodoDragon | komodoDragon |  | UEM_komodoDragon_M_char [0, 1] | 1.0 | 30.0/50.0 |  | KomodoDragonSounds |
| 169 | 0xA9 | TreePine | treePine |  | UEM_treePine_M_char [0, 1] | 1.0 | 1250.0/60.0 |  |  |
| 170 | 0xAA | Cyclops | cyclops |  | UEM_cyclops_M_char [0] | 2.24 | 225.0/70.0 |  | CyclopsSounds |
| 171 | 0xAB | Dryad |  | dryad | UEM_dryad_F_char [0] | 1.0 | 90.0/30.0 |  |  |
| 172 | 0xAC | RockOre | rockOre |  | UEM_rockOre_M_char [0, 1, 2, 3] | 1.0 | 50.0/60.0 |  |  |
| 173 | 0xAD | Beetle | beetle |  | UEM_beetle_M_char [0, 1, 2, 3] | 1.0 | 40.0/50.0 |  | ScarabSounds |
| 174 | 0xAE | PlantAlchemical | PlantAlchemical |  | UEM_PlantAlchemical_M_char [0, 1, 2, 3, 4, 5, 6, 7] | 1.0 | 55.0/65.0 |  |  |
| 175 | 0xAF | PlantTextile | PlantTextile |  | UEM_PlantTextile_M_char [0, 1, 2, 3, 4] | 1.0 | 55.0/55.0 |  |  |
| 176 | 0xB0 | RockMineral | rockMineral |  | UEM_rockMineral_M_char [0, 1, 2, 3] | 1.0 | 50.0/60.0 |  |  |
| 177 | 0xB1 | Brownie | brownie |  | UEM_brownie_M_char [0, 1, 2, 3, 4] | 0.5 | 40.0/12.0 |  | BrownieSounds |
| 178 | 0xB2 | BearZombie | bearUndead |  | UEM_bearUndead_M_char [0] | 1.0 | 70.0/50.0 | 0 | BearUndeadSounds |
| 179 | 0xB3 | HorseQuarter | horseQuarter |  | UEM_horseQuarter_M_char [0, 1] | 1.2 | 110.0/50.0 |  | QuarterHorseSounds |
| 180 | 0xB4 | TreeAsh | treeAsh |  | UEM_treeAsh_M_char [0, 1] | 1.0 | 1250.0/60.0 |  |  |
| 181 | 0xB5 | TreeAspen | treeAspen |  | UEM_treeAspen_M_char [0] | 1.0 | 1250.0/60.0 |  |  |
| 182 | 0xB6 | TreeBeech | treeBeech |  | UEM_treeBeech_M_char [0, 1] | 1.0 | 1200.0/100.0 |  |  |
| 183 | 0xB7 | TreeCottonwood | treeCottonwood |  | UEM_treeCottonwood_M_char [0] | 1.0 | 1300.0/100.0 |  |  |
| 184 | 0xB8 | TreeOak | treeOak |  | UEM_treeOak_M_char [0, 1] | 1.0 | 1000.0/100.0 |  |  |
| 185 | 0xB9 | BearSkeleton | bearUndead |  | UEM_bearUndead_M_char [0] | 1.0 | 70.0/50.0 | 1 | BearUndeadSounds |
| 186 | 0xBA | NPCDwarf | npcDwarf | npcDwarf | UEM_npcDwarf_M_char [0, 10, 11] / UEM_npcDwarf_F_char [0, 10] | 1.11 | 75.0/22.5 |  | Dwarf_Male_ASounds |
| 187 | 0xBB | NPCDarkElf | npcElf | npcElf | UEM_npcElf_M_char [0, 1, 2, 4, 10, 11, 12, 13, 20, 30, 40, 50, 60] / UEM_npcElf_F_char [0, 1, 2, 4, 10, 11, 12, 13, 20, 30, 40, 50] | 1.056 | 90.0/27.0 | 1 | Elf_Male_Q_ASounds |
| 188 | 0xBC | NPCHighElf | npcElf | npcElf | UEM_npcElf_M_char [0, 1, 2, 4, 10, 11, 12, 13, 20, 30, 40, 50, 60] / UEM_npcElf_F_char [0, 1, 2, 4, 10, 11, 12, 13, 20, 30, 40, 50] | 1.056 | 90.0/27.0 |  | Elf_Male_T_ASounds |
| 189 | 0xBD | NPCWoodElf | npcElf | npcElf | UEM_npcElf_M_char [0, 1, 2, 4, 10, 11, 12, 13, 20, 30, 40, 50, 60] / UEM_npcElf_F_char [0, 1, 2, 4, 10, 11, 12, 13, 20, 30, 40, 50] | 1.056 | 90.0/27.0 | 2 | Elf_Male_K_ASounds |
| 190 | 0xBE | NPCGnome | npcGnome | npcGnome | UEM_npcGnome_M_char [0, 10, 11] / UEM_npcGnome_F_char [0, 10] | 0.8 | 60.0/18.0 |  | Gnome_Male_ASounds |
| 191 | 0xBF | NPCGoblin | npcGoblin | npcGoblin | UEM_npcGoblin_M_char [0, 1, 10, 11, 12, 20, 30] / UEM_npcGoblin_F_char [0, 1, 10, 20, 30] | 0.833 | 75.0/22.5 |  | Goblin_Male_ASounds |
| 192 | 0xC0 | NPCHalfElf | npcHalfElf | npcHalfElf | UEM_npcHalfElf_M_char [0, 10] / UEM_npcHalfElf_F_char [0, 10] | 1.0 | 90.0/27.0 |  | HalfElf_Male_ASounds |
| 193 | 0xC1 | NPCLesserGiant | npcHalfGiant | npcHalfGiant | UEM_npcHalfGiant_M_char [0, 10] / UEM_npcHalfGiant_F_char [0, 10] | 1.238 | 105.0/31.5 |  | Giant_Male_ASounds |
| 194 | 0xC2 | NPCHalfling | npcHalfling | npcHalfling | UEM_npcHalfling_M_char [0, 10] / UEM_npcHalfling_F_char [0, 10] | 0.658 | 60.0/18.0 |  | Halfling_Male_ASounds |
| 195 | 0xC3 | NPCHalfOrc | npcHalfOrc | npcHalfOrc | (no M; MISSING) / (no F; MISSING) | 1.0 | 90.0/27.0 |  |  |
| 196 | 0xC4 | NPCKojanHuman | npcHuman | npcHuman | UEM_npcHuman_M_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 32, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 131] / UEM_npcHuman_F_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 104] | 1.0 | 90.0/27.0 | 2 | Human_Male_K_ASounds |
| 197 | 0xC5 | NPCQaliathari | npcHuman | npcHuman | UEM_npcHuman_M_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 32, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 131] / UEM_npcHuman_F_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 104] | 1.0 | 90.0/27.0 | 3 | Human_Male_Q_ASounds |
| 198 | 0xC6 | NPCThestran | npcHuman | npcHuman | UEM_npcHuman_M_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 32, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 131] / UEM_npcHuman_F_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 104] | 1.0 | 90.0/27.0 |  | Human_Male_T_ASounds |
| 199 | 0xC7 | NPCMordebi | npcHuman | npcHuman | UEM_npcHuman_M_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 32, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 131] / UEM_npcHuman_F_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 104] | 1.0 | 90.0/27.0 | 1 | Mordebi_Male_ASounds |
| 200 | 0xC8 | NPCOrc | npcOrc | npcOrc | UEM_npcOrc_M_char [0, 1, 10, 11, 12, 20, 30] / UEM_npcOrc_F_char [0, 1, 10, 20, 30] | 1.005 | 90.4/27.1 |  | Orc_Male_ASounds |
| 201 | 0xC9 | NPCRaki | npcRaki | npcRaki | UEM_npcRaki_M_char [0, 10] / UEM_npcRaki_F_char [0, 10] | 0.85 | 60.0/18.0 |  | Raki_Male_ASounds |
| 202 | 0xCA | NPCVulmane | npcVulmane | npcVulmane | UEM_npcVulmane_M_char [0, 1, 10, 11] / UEM_npcVulmane_F_char [0, 1, 10, 11] | 1.136 | 97.5/29.25 |  | Vulmane_Male_ASounds |
| 203 | 0xCB | NPCKojanBarbarian | npcKojanBarbarian | npcKojanBarbarian | (no M; MISSING) / (no F; MISSING) | 1.0 | 90.0/27.0 |  |  |
| 204 | 0xCC | NPCVaranthari | npcBarbarian | npcBarbarian | UEM_npcBarbarian_M_char [0, 1, 10, 11] / UEM_npcBarbarian_F_char [0, 1, 10, 11] | 1.088 | 97.5/29.25 | 1 | Barbarian_Male_Q_ASounds |
| 205 | 0xCD | NPCVaranjar | npcBarbarian | npcBarbarian | UEM_npcBarbarian_M_char [0, 1, 10, 11] / UEM_npcBarbarian_F_char [0, 1, 10, 11] | 1.088 | 97.5/29.25 |  | Barbarian_Male_T_ASounds |
| 206 | 0xCE | NPCKurashasa | npcKura | npcKura | UEM_npcKura_M_char [0, 10, 11] / UEM_npcKura_F_char [0, 10, 11] | 1.151 | 97.5/29.25 |  | Kurashasa_Male_ASounds |
| 207 | 0xCF | InvisibleMan | npcHuman | npcHuman | UEM_npcHuman_M_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 32, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 131] / UEM_npcHuman_F_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 104] | 1.0 | 90.0/27.0 | 99 |  |
| 208 | 0xD0 | ForgeThestra | forgeThestra |  | UEM_forgeThestra_M_char [0] | 1.0 | 150.0/150.0 |  |  |
| 209 | 0xD1 | SmelterThestra | smelterThestra |  | UEM_smelterThestra_M_char [0] | 1.0 | 135.0/150.0 |  |  |
| 210 | 0xD2 | HorseShetland | horseShetland |  | UEM_horseShetland_M_char [0] | 1.2 | 110.0/50.0 |  | QuarterHorseSounds |
| 211 | 0xD3 | HorseShire | horseShire |  | UEM_horseShire_M_char [0, 1] | 1.2 | 110.0/50.0 |  | QuarterHorseSounds |
| 212 | 0xD4 | EarthElemental | elementalEarth |  | UEM_elementalEarth_M_char [0, 1, 2, 3, 4, 5] | 1.0 | 100.0/50.0 |  | ElementalEarthSounds |
| 213 | 0xD5 | MetalGolem | golemMetal |  | UEM_golemMetal_M_char [0, 1, 2, 11, 20, 21, 99] | 2.24 | 150.0/50.0 | 2 | MetalGolemSounds |
| 214 | 0xD6 | FinishingTableThestra | finishingtableThestra |  | UEM_finishingtableThestra_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 215 | 0xD7 | SawTableThestra | sawtableThestra |  | UEM_sawtableThestra_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 216 | 0xD8 | FireElemental | elementalFire |  | UEM_elementalFire_M_char [0, 1, 2, 3, 4, 5, 13] | 1.0 | 100.0/50.0 |  | FireElementalSounds |
| 217 | 0xD9 | Fox | fox |  | UEM_fox_M_char [0, 1] | 1.0 | 40.0/25.0 |  | FoxSounds |
| 218 | 0xDA | BearDire | bearDire |  | UEM_bearDire_M_char [0, 1] | 1.0 | 70.0/50.0 |  | BearDireSounds |
| 219 | 0xDB | WolfZombie | wolfUndead |  | UEM_wolfUndead_M_char [0] | 1.0 | 40.0/25.0 | 0 | WolfUndeadSounds |
| 220 | 0xDC | WolfSkeleton | wolfUndead |  | UEM_wolfUndead_M_char [0] | 1.0 | 40.0/25.0 | 1 | WolfUndeadSounds |
| 221 | 0xDD | WolfDire | wolfDire |  | UEM_wolfDire_M_char [0, 1, 2, 3, 4] | 1.0 | 40.0/25.0 |  | WolfDireSounds |
| 222 | 0xDE | Deer | deer | deer | UEM_deer_M_char [0, 1, 11] / UEM_deer_F_char [0] | 1.0 | 100.0/40.0 |  | ElkSounds |
| 223 | 0xDF | Gorgon |  | gorgon | UEM_gorgon_F_char [0, 1, 2] | 1.0 | 90.0/30.0 |  |  |
| 224 | 0xE0 | TentacleLord | tentacleLord |  | UEM_tentacleLord_M_char [0, 1, 2, 3] | 1.0 | 90.0/30.0 |  | XennumetSounds |
| 225 | 0xE1 | SandGiant | giantSand |  | UEM_giantSand_M_char [0, 1] | 1.0 | 85.0/30.0 |  | GiantSounds |
| 226 | 0xE2 | Elk | elk |  | UEM_elk_M_char [0] | 1.0 | 100.0/40.0 |  | ElkSounds |
| 227 | 0xE3 | Wyrm | wyrm |  | UEM_wyrm_M_char [0, 10, 20, 30, 31, 40, 50, 60, 70, 80, 90, 95, 96, 97, 98, 99, 100] | 2.0 | 200.0/50.0 |  | WyrmSounds |
| 228 | 0xE4 | DressTest | human | human | UEM_human_M_char [0, 1, 2, 3] / UEM_human_F_char [0, 1, 2, 3] | 1.0 | 90.0/27.0 |  | Human_Male_T_ASounds |
| 229 | 0xE5 | RockCaveIn | RockCaveIn |  | UEM_RockCaveIn_M_char [0] | 1.0 | 500.0/600.0 |  |  |
| 230 | 0xE6 | AntLion | antLion |  | UEM_antLion_M_char [0, 1] | 1.0 | 70.0/60.0 |  | AntLionSounds |
| 231 | 0xE7 | Hellhound | hellhound |  | UEM_hellhound_M_char [0, 1, 2] | 1.0 | 40.0/30.0 |  | HellhoundSounds |
| 232 | 0xE8 | Jackal | jackal |  | UEM_jackal_M_char [0, 1] | 1.0 | 50.0/100.0 |  | JackalSounds |
| 233 | 0xE9 | Undead | undead | undead | UEM_undead_M_char [0, 1] / UEM_undead_F_char [0, 1] | 1.0 | 90.0/30.0 |  | ZombieMaleSounds |
| 234 | 0xEA | Lion | catLion | catLion | UEM_catLion_M_char [0, 10] / UEM_catLion_F_char [0] | 1.0 | 75.0/30.0 |  | LionMaleSounds |
| 235 | 0xEB | Tiger | catTiger | catTiger | UEM_catTiger_M_char [0] / (no F; falls back to cattiger_m_char [0]) | 1.0 | 75.0/30.0 |  | TigerSounds |
| 236 | 0xEC | Leopard | catLeopard | catLeopard | UEM_catLeopard_M_char [0, 1] / (no F; falls back to catleopard_m_char [0, 1]) | 1.0 | 75.0/30.0 |  | LeopardSounds |
| 237 | 0xED | Panther | catPanther | catPanther | UEM_catPanther_M_char [0, 1] / (no F; falls back to catpanther_m_char [0, 1]) | 1.0 | 75.0/30.0 |  | PantherSounds |
| 238 | 0xEE | Cougar | catCougar | catCougar | UEM_catCougar_M_char [0, 1] / (no F; falls back to catcougar_m_char [0, 1]) | 1.0 | 75.0/30.0 |  | CougarSounds |
| 239 | 0xEF | StormElemental | elementalStorm |  | UEM_elementalStorm_M_char [0, 1, 2, 3, 4] | 1.0 | 90.0/30.0 |  | StormElementalSounds |
| 240 | 0xF0 | Demilich | demilich |  | UEM_demilich_M_char [0] | 1.0 | 90.0/30.0 |  | DemiLichSounds |
| 241 | 0xF1 | DeathKnight | deathKnight | deathKnight | UEM_deathKnight_M_char [0] / UEM_deathKnight_F_char [0] | 1.0 | 90.0/30.0 |  | DeathKnightSounds |
| 242 | 0xF2 | Mantis | mantis | mantis | UEM_mantis_M_char [0] / UEM_mantis_F_char [0, 1, 2] | 1.0 | 90.0/30.0 |  | MantisSounds |
| 243 | 0xF3 | WispElemental | elementalWisp |  | UEM_elementalWisp_M_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76] | 1.0 | 100.0/30.0 |  | WillowispSounds |
| 244 | 0xF4 | MistElemental | elementalMist |  | UEM_elementalMist_M_char [0, 1, 2, 3, 4] | 1.0 | 100.0/30.0 |  | WillowispSounds |
| 245 | 0xF5 | HorseUndead | horseUndead |  | UEM_horseUndead_M_char [0, 1] | 1.2 | 110.0/50.0 |  | HorseUndeadSounds |
| 246 | 0xF6 | HorseSkeleton | horseSkeleton |  | UEM_horseSkeleton_M_char [0] | 1.2 | 110.0/50.0 |  | HorseUndeadSounds |
| 247 | 0xF7 | Minotaur | minotaur |  | UEM_minotaur_M_char [0, 1] | 1.5 | 225.0/50.0 |  | MinotaurSounds |
| 248 | 0xF8 | TextileTableThestra | textiletableThestra |  | UEM_textiletableThestra_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 249 | 0xF9 | SewingTableThestra | SewingTableThestra |  | UEM_SewingTableThestra_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 250 | 0xFA | Giant | giant |  | UEM_giant_M_char [0, 1] | 3.0 | 270.0/90.0 |  | GiantSounds |
| 251 | 0xFB | EyeLord | eyeLord |  | UEM_eyeLord_M_char [0, 1] | 1.0 | 100.0/50.0 |  | EyeLordSounds |
| 252 | 0xFC | Mummy | mummy |  | UEM_mummy_M_char [0, 1] | 1.0 | 90.0/30.0 |  | MummySounds |
| 253 | 0xFD | TurtleDragon | turtleDragon |  | UEM_turtleDragon_M_char [0, 1] | 1.0 | 50.0/100.0 |  | TurtleDragonSounds |
| 254 | 0xFE | TurtleDragonSea | turtleDragonSea |  | (no M; MISSING) | 1.0 | 50.0/100.0 |  | TurtleDragonSounds |
| 255 | 0xFF | Ghast | ghoul |  | UEM_ghoul_M_char [0, 1, 10] | 1.0 | 90.0/30.0 |  | GhoulSounds |
| 256 | 0x100 | StatueAnubis | statueAnubis |  | UEM_statueAnubis_M_char [0] | 1.0 | 90.0/30.0 |  | AnubisStatueSounds |
| 257 | 0x101 | StatueCat | statueCat |  | UEM_statueCat_M_char [0, 1, 2] | 1.0 | 50.0/25.0 |  | CatStatueSounds |
| 258 | 0x102 | JharuuWarrior | jharuuWarrior |  | UEM_jharuuWarrior_M_char [0] | 1.0 | 104.0/60.0 |  | JharuuSounds |
| 259 | 0x103 | CatDomestic | catDomestic |  | UEM_catDomestic_M_char [0] | 1.0 | 60.0/45.0 |  | CatSounds |
| 260 | 0x104 | Phoenix | raptorPhoenix |  | UEM_raptorPhoenix_M_char [0, 1, 5, 10] | 1.0 | 75.0/30.0 |  | PhoenixSounds |
| 261 | 0x105 | Raven | birdRaven |  | UEM_birdRaven_M_char [0] | 1.0 | 75.0/30.0 |  | RavenSounds |
| 262 | 0x106 | Hyena | hyena |  | UEM_hyena_M_char [0, 1] | 1.0 | 40.0/30.0 |  | HyenaSounds |
| 263 | 0x107 | Camel | camel |  | UEM_camel_M_char [0, 1] | 1.3 | 125.0/45.0 |  | CamelSounds |
| 264 | 0x108 | Seagull | birdSeagull |  | UEM_birdSeagull_M_char [0] | 1.0 | 75.0/30.0 |  | SeagullSounds |
| 265 | 0x109 | Hawk | raptorHawk |  | UEM_raptorHawk_M_char [0] | 1.0 | 75.0/30.0 |  | HawkSounds |
| 266 | 0x10A | Falcon | raptorFalcon |  | UEM_raptorFalcon_M_char [0] | 1.0 | 75.0/30.0 |  | HawkSounds |
| 267 | 0x10B | Eagle | raptorEagle |  | UEM_raptorEagle_M_char [0, 1, 10] | 1.0 | 75.0/30.0 |  | EagleSounds |
| 268 | 0x10C | Roc | raptorRoc |  | UEM_raptorRoc_M_char [0, 1] | 1.0 | 75.0/30.0 |  | RocSounds |
| 269 | 0x10D | Vulture | raptorVulture |  | UEM_raptorVulture_M_char [0] | 1.0 | 75.0/30.0 |  | VultureSounds |
| 270 | 0x10E | Abomination | abomination |  | UEM_abomination_M_char [0] | 1.0 | 50.0/30.0 |  | AbominationSounds |
| 271 | 0x10F | Siren |  | siren | UEM_siren_F_char [0, 10] | 1.0 | 90.0/30.0 |  |  |
| 272 | 0x110 | Efreet | efreet |  | UEM_efreet_M_char [0, 10] | 1.0 | 85.0/30.0 |  | EfreetSounds |
| 273 | 0x111 | Gazelle | gazelle |  | UEM_gazelle_M_char [0] | 1.0 | 75.0/30.0 |  | ElkSounds |
| 274 | 0x112 | GilaMonster | gilaMonster |  | UEM_gilaMonster_M_char [0, 1] | 1.0 | 18.0/25.0 |  | KomodoDragonSounds |
| 275 | 0x113 | MountainGoat | goatMountain |  | UEM_goatMountain_M_char [0] | 1.0 | 80.0/35.0 |  | RamSounds |
| 276 | 0x114 | Unicorn | unicorn |  | UEM_unicorn_M_char [0, 1, 2] | 1.2 | 110.0/50.0 |  | PegasusSounds |
| 277 | 0x115 | Vampire |  | vampire | UEM_vampire_F_char [0, 10, 11] | 1.0 | 90.0/30.0 |  |  |
| 278 | 0x116 | PlayerSkeleton | skeleton | skeleton | UEM_skeleton_M_char [0, 1, 2, 3, 10, 13, 23] / UEM_skeleton_F_char [0, 10] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 279 | 0x117 | PlayerLich | lich | lich | UEM_lich_M_char [0, 10, 20] / UEM_lich_F_char [0, 10] | 1.0 | 90.0/30.0 |  | LichMaleSounds |
| 280 | 0x118 | FleshGolem | golemFlesh |  | UEM_golemFlesh_M_char [0, 2] | 1.0 | 90.0/32.0 |  | FleshGolemSounds |
| 281 | 0x119 | Corpse |  | corpse | UEM_corpse_F_char [0] | 1.0 | 90.0/30.0 |  |  |
| 282 | 0x11A | Gargoyle | gargoyle |  | UEM_gargoyle_M_char [0, 1, 2, 10, 11, 12, 20, 21, 30, 31] | 1.0 | 200.0/55.0 |  | GargoyleSounds |
| 283 | 0x11B | VultureMan | vultureMan |  | UEM_vultureMan_M_char [0, 1, 10, 11] | 1.0 | 90.0/75.0 |  | VulturemanSounds |
| 284 | 0x11C | ShamblingShell | shamblingShell |  | UEM_shamblingShell_M_char [0] | 1.0 | 120.0/60.0 |  | ShamblingShellSounds |
| 285 | 0x11D | RockDervish | rockDervish |  | UEM_rockDervish_M_char [0] | 1.0 | 60.0/30.0 |  | RockDervishSounds |
| 286 | 0x11E | SeaHag |  | seaHag | UEM_seaHag_F_char [0, 10, 11] | 1.0 | 90.0/30.0 |  |  |
| 287 | 0x11F | SeaLord | seaLord |  | UEM_seaLord_M_char [0, 10] | 1.0 | 80.0/33.0 |  | SeaHagLordSounds |
| 288 | 0x120 | Lizardman | lizardMan |  | UEM_lizardMan_M_char [0] | 1.0 | 85.0/30.0 |  | LizardmanSounds |
| 289 | 0x121 | Mudman | mudman |  | UEM_mudman_M_char [0, 1] | 1.0 | 85.0/30.0 |  | MudmanSounds |
| 290 | 0x122 | WarehouseGuardian | GuardianWarehouse |  | UEM_GuardianWarehouse_M_char [0, 1] | 1.0 | 85.0/35.0 |  | MetalGolemSounds |
| 291 | 0x123 | KoboldChieftain | koboldChieftain |  | UEM_koboldChieftain_M_char [0] | 1.0 | 70.0/40.0 |  | KoboldChiefSounds |
| 292 | 0x124 | ShamblingMoundDesert | shamblingMound |  | UEM_shamblingMound_M_char [0, 2, 10, 20] | 1.0 | 120.0/60.0 | 2 | ShamblingMoundSounds |
| 293 | 0x125 | VenomousFrog | venomousFrog |  | UEM_venomousFrog_M_char [0] | 1.0 | 50.0/60.0 |  | ToadSounds |
| 294 | 0x126 | FunnelTextile | FunnelTextile |  | UEM_FunnelTextile_M_char [0] | 1.0 | 55.0/60.0 |  |  |
| 295 | 0x127 | MushroomAlchemical | MushroomAlchemical |  | UEM_MushroomAlchemical_M_char [0] | 1.0 | 48.0/65.0 |  |  |
| 296 | 0x128 | RootWood | RootWood |  | UEM_RootWood_M_char [0] | 1.0 | 22.0/50.0 |  |  |
| 297 | 0x129 | CoastalLampray | coastallampray |  | UEM_coastallampray_M_char [0] | 1.0 | 20.0/40.0 |  | LampreySounds |
| 298 | 0x12A | PlayerWraith | wraith | wraith | UEM_wraith_M_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] / UEM_wraith_F_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 299 | 0x12B | PlayerZombie | skeleton | skeleton | UEM_skeleton_M_char [0, 1, 2, 3, 10, 13, 23] / UEM_skeleton_F_char [0, 10] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 300 | 0x12C | PlayerMummy | skeleton | skeleton | UEM_skeleton_M_char [0, 1, 2, 3, 10, 13, 23] / UEM_skeleton_F_char [0, 10] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 301 | 0x12D | PlayerDeathKnight | deathknight | deathknight | UEM_deathknight_M_char [0] / UEM_deathknight_F_char [0] | 1.0 | 90.0/30.0 |  | DeathKnightSounds |
| 302 | 0x12E | PlayerGhost | skeleton | skeleton | UEM_skeleton_M_char [0, 1, 2, 3, 10, 13, 23] / UEM_skeleton_F_char [0, 10] | 1.0 | 90.0/30.0 |  | SkeletonMaleSounds |
| 303 | 0x12F | Pegasus | pegasus |  | UEM_pegasus_M_char [0, 1, 10, 11, 12, 13, 14, 15, 20, 21, 22, 23, 24] | 1.2 | 110.0/50.0 |  | PegasusSounds |
| 304 | 0x130 | PlayerPine | treePine | treePine | UEM_treePine_M_char [0, 1] / (no F; falls back to treepine_m_char [0, 1]) | 0.2 | 90.0/30.0 | 1 |  |
| 305 | 0x131 | PlayerAsh | treeAsh | treeAsh | UEM_treeAsh_M_char [0, 1] / (no F; falls back to treeash_m_char [0, 1]) | 0.2 | 90.0/30.0 | 1 |  |
| 306 | 0x132 | PlayerBeech | treeBeech | treeBeech | UEM_treeBeech_M_char [0, 1] / (no F; falls back to treebeech_m_char [0, 1]) | 0.2 | 90.0/30.0 | 1 |  |
| 307 | 0x133 | PlayerOak | treeOak | treeOak | UEM_treeOak_M_char [0, 1] / (no F; falls back to treeoak_m_char [0, 1]) | 0.2 | 90.0/30.0 | 1 |  |
| 308 | 0x134 | NecroGolem | golemFlesh |  | UEM_golemFlesh_M_char [0, 2] | 1.0 | 90.0/32.0 | 2 | FleshGolemSounds |
| 309 | 0x135 | PlagueBearer | zombie | zombie | UEM_zombie_M_char [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 20, 21] / UEM_zombie_F_char [0, 1, 12] | 1.0 | 90.0/30.0 | 2 | ZombieMaleSounds |
| 310 | 0x136 | Trap | npcHuman |  | UEM_npcHuman_M_char [0, 1, 2, 3, 10, 11, 12, 13, 14, 22, 32, 42, 52, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 131] | 1.0 | 90.0/27.0 | 100 |  |
| 311 | 0x137 | ZombieDwarf | zombie | zombie | UEM_zombie_M_char [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 20, 21] / UEM_zombie_F_char [0, 1, 12] | 1.11 | 75.0/22.5 | 3 | ZombieMaleSounds |
| 312 | 0x138 | ZombieGnome | zombie | zombie | UEM_zombie_M_char [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 20, 21] / UEM_zombie_F_char [0, 1, 12] | 0.8 | 60.0/18.0 | 6 | ZombieMaleSounds |
| 313 | 0x139 | TreePurpleBerry | treePurpleBerry |  | UEM_treePurpleBerry_M_char [0] | 1.0 | 375.0/40.0 |  |  |
| 314 | 0x13A | WolfOkami | wolfOkami |  | UEM_wolfOkami_M_char [0, 1, 2, 3, 10] | 1.0 | 40.0/25.0 |  | OkamiSounds |
| 315 | 0x13B | Sahaugin | sahaugin |  | UEM_sahaugin_M_char [0] | 1.0 | 120.0/45.0 |  | AquaSalamanderSounds |
| 316 | 0x13C | ElementalGolem | golemElemental |  | UEM_golemElemental_M_char [0, 1, 10, 11, 12, 20, 21, 30, 31, 40, 41, 50, 51, 60, 61, 70, 71, 80, 81, 90, 91, 95, 96, 97, 98] | 1.0 | 90.0/30.0 |  | ElemGolemSounds |
| 317 | 0x13D | RockGolem | golemRock |  | UEM_golemRock_M_char [0, 1] | 1.0 | 90.0/35.0 |  | ElemGolemSounds |
| 318 | 0x13E | FungusMan | fungusMan |  | UEM_fungusMan_M_char [0, 1] | 1.0 | 90.0/35.0 |  | MyconidSounds |
| 319 | 0x13F | SharkGreatWhite | sharkGreatWhite |  | UEM_sharkGreatWhite_M_char [0] | 1.0 | 35.0/40.0 |  | GarSounds |
| 320 | 0x140 | FishBass | fishBass |  | (no M; MISSING) | 1.0 | 40.0/30.0 |  | BassSounds |
| 321 | 0x141 | FishGar | fishGar |  | (no M; MISSING) | 1.0 | 40.0/30.0 |  | GarSounds |
| 322 | 0x142 | WhaleHumpback | whaleHumpback |  | UEM_whaleHumpback_M_char [0, 10] | 1.0 | 30.0/45.0 |  | GarSounds |
| 323 | 0x143 | WhaleOrca | whaleOrca |  | UEM_whaleOrca_M_char [0, 1] | 1.0 | 60.0/45.0 |  | GarSounds |
| 324 | 0x144 | WhaleDolphin | whaleDolphin |  | UEM_whaleDolphin_M_char [0] | 1.0 | 40.0/35.0 |  | GarSounds |
| 325 | 0x145 | Dragon | dragon |  | UEM_dragon_M_char [0, 1, 2] | 1.0 | 70.0/100.0 |  | WyrmSounds |
| 326 | 0x146 | DireLobster | direlobster |  | UEM_direlobster_M_char [0, 1] | 1.0 | 65.0/65.0 |  | CrabSounds |
| 327 | 0x147 | DragonBlack | dragon_Black |  | UEM_dragon_Black_M_char [0, 1, 2, 3, 4] | 1.0 | 70.0/100.0 |  | WyrmSounds |
| 328 | 0x148 | DragonSwamp | dragon_Swamp |  | UEM_dragon_Swamp_M_char [0, 1, 2] | 1.0 | 70.0/100.0 |  | Dragon_Swamp_MSounds |
| 329 | 0x149 | CartheonKnight | cartheonKnight |  | UEM_cartheonKnight_M_char [0, 1] | 1.0 | 95.0/40.0 |  | DeathKnightSounds |
| 330 | 0x14A | Crystal | crystal |  | UEM_crystal_M_char [0, 1, 2, 3, 4, 5] | 1.0 | 665.0/85.0 |  |  |
| 331 | 0x14B | Sporebeast | sporebeast |  | UEM_sporebeast_M_char [0] | 1.0 | 146.0/60.0 |  | TrollSounds |
| 332 | 0x14C | CartheonNecromancer | cartheonNecromancer |  | UEM_cartheonNecromancer_M_char [0, 1, 10] | 1.0 | 95.0/30.0 |  | DeathKnightSounds |
| 333 | 0x14D | Banshee |  | banshee | UEM_banshee_F_char [0, 1] | 1.0 | 90.0/30.0 |  |  |
| 334 | 0x14E | Hydrospore | hydrospore |  | UEM_hydrospore_M_char [0, 1] | 1.0 | 136.0/150.0 |  | SwamphibianBossSounds |
| 335 | 0x14F | Drakeling | drakeling |  | UEM_drakeling_M_char [0] | 1.0 | 70.0/40.0 |  | DrakeSounds |
| 336 | 0x150 | WyrmWingless | wyrmWingless |  | UEM_wyrmWingless_M_char [0, 1] | 2.0 | 115.0/75.0 |  | WyrmSounds |
| 337 | 0x151 | ForgeKojan | forgeKojan |  | UEM_forgeKojan_M_char [0] | 1.0 | 150.0/150.0 |  |  |
| 338 | 0x152 | FinishingTableKojan | finishingtableKojan |  | UEM_finishingtableKojan_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 339 | 0x153 | FinishingTableQalia | finishingtableQalia |  | UEM_finishingtableQalia_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 340 | 0x154 | SawTableKojan | sawTableKojan |  | UEM_sawTableKojan_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 341 | 0x155 | SawTableQalia | sawtableQalia |  | UEM_sawtableQalia_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 342 | 0x156 | SewingTableKojan | sewingtableKojan |  | UEM_sewingtableKojan_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 343 | 0x157 | SewingTableQalia | sewingtableQalia |  | UEM_sewingtableQalia_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 344 | 0x158 | SmelterKojan | smelterKojan |  | UEM_smelterKojan_M_char [0] | 1.0 | 135.0/150.0 |  |  |
| 345 | 0x159 | TextileTableKojan | textileTableKojan |  | UEM_textileTableKojan_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 346 | 0x15A | TextileTableQalia | textiletableQalia |  | UEM_textiletableQalia_M_char [0] | 1.0 | 40.0/75.0 |  |  |
| 347 | 0x15B | BlockingWispElemental | elementalWisp |  | UEM_elementalWisp_M_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76] | 1.0 | 208.0/82.8 |  | WillowispSounds |
| 348 | 0x15C | OPTDwarf | optimizedDwarf | optimizedDwarf | UEM_optimizedDwarf_M_char [0] / UEM_optimizedDwarf_F_char [0] | 1.11 | 75.0/22.5 |  | Dwarf_Male_ASounds |
| 349 | 0x15D | OPTDarkElf | optimizedElf | optimizedElf | UEM_optimizedElf_M_char [0, 1, 2] / UEM_optimizedElf_F_char [0, 1, 2] | 1.056 | 90.0/27.0 | 1 | Elf_Male_Q_ASounds |
| 350 | 0x15E | OPTHighElf | optimizedElf | optimizedElf | UEM_optimizedElf_M_char [0, 1, 2] / UEM_optimizedElf_F_char [0, 1, 2] | 1.056 | 90.0/27.0 |  | Elf_Male_T_ASounds |
| 351 | 0x15F | OPTWoodElf | optimizedElf | optimizedElf | UEM_optimizedElf_M_char [0, 1, 2] / UEM_optimizedElf_F_char [0, 1, 2] | 1.056 | 90.0/27.0 | 2 | Elf_Male_K_ASounds |
| 352 | 0x160 | OPTGnome | optimizedGnome | optimizedGnome | UEM_optimizedGnome_M_char [0] / UEM_optimizedGnome_F_char [0] | 0.8 | 60.0/18.0 |  | Gnome_Male_ASounds |
| 353 | 0x161 | OPTGoblin | optimizedGoblin | optimizedGoblin | UEM_optimizedGoblin_M_char [0] / UEM_optimizedGoblin_F_char [0] | 0.833 | 75.0/22.5 |  | Goblin_Male_ASounds |
| 354 | 0x162 | OPTHalfElf | optimizedHalfElf | optimizedHalfElf | UEM_optimizedHalfElf_M_char [0] / UEM_optimizedHalfElf_F_char [0] | 1.0 | 90.0/27.0 |  | HalfElf_Male_ASounds |
| 355 | 0x163 | OPTLesserGiant | optimizedHalfGiant | optimizedHalfGiant | UEM_optimizedHalfGiant_M_char [0] / UEM_optimizedHalfGiant_F_char [0] | 1.238 | 105.0/31.5 |  | Giant_Male_ASounds |
| 356 | 0x164 | OPTHalfling | optimizedHalfling | optimizedHalfling | UEM_optimizedHalfling_M_char [0] / UEM_optimizedHalfling_F_char [0] | 0.658 | 60.0/18.0 |  | Halfling_Male_ASounds |
| 357 | 0x165 | OPTHalfOrc | optimizedHalfOrc | optimizedHalfOrc | (no M; MISSING) / (no F; MISSING) | 1.0 | 90.0/27.0 |  |  |
| 358 | 0x166 | OPTKojanHuman | optimizedHuman | optimizedHuman | UEM_optimizedHuman_M_char [0, 1, 2, 3, 10, 20, 30, 40, 86, 90, 91, 92, 93, 100] / UEM_optimizedHuman_F_char [0, 1, 2, 3, 90, 91, 92, 93] | 1.0 | 90.0/27.0 | 2 | Human_Male_K_ASounds |
| 359 | 0x167 | OPTQaliathari | optimizedHuman | optimizedHuman | UEM_optimizedHuman_M_char [0, 1, 2, 3, 10, 20, 30, 40, 86, 90, 91, 92, 93, 100] / UEM_optimizedHuman_F_char [0, 1, 2, 3, 90, 91, 92, 93] | 1.0 | 90.0/27.0 | 3 | Human_Male_Q_ASounds |
| 360 | 0x168 | OPTThestran | optimizedHuman | optimizedHuman | UEM_optimizedHuman_M_char [0, 1, 2, 3, 10, 20, 30, 40, 86, 90, 91, 92, 93, 100] / UEM_optimizedHuman_F_char [0, 1, 2, 3, 90, 91, 92, 93] | 1.0 | 90.0/27.0 |  | Human_Male_T_ASounds |
| 361 | 0x169 | OPTMordebi | optimizedHuman | optimizedHuman | UEM_optimizedHuman_M_char [0, 1, 2, 3, 10, 20, 30, 40, 86, 90, 91, 92, 93, 100] / UEM_optimizedHuman_F_char [0, 1, 2, 3, 90, 91, 92, 93] | 1.0 | 90.0/27.0 | 1 | Mordebi_Male_ASounds |
| 362 | 0x16A | OPTOrc | optimizedOrc | optimizedOrc | UEM_optimizedOrc_M_char [0] / UEM_optimizedOrc_F_char [0] | 1.005 | 90.4/27.1 |  | Orc_Male_ASounds |
| 363 | 0x16B | OPTRaki | optimizedRaki | optimizedRaki | UEM_optimizedRaki_M_char [0] / UEM_optimizedRaki_F_char [0] | 0.85 | 60.0/18.0 |  | Raki_Male_ASounds |
| 364 | 0x16C | OPTVulmane | optimizedVulmane | optimizedVulmane | UEM_optimizedVulmane_M_char [0] / UEM_optimizedVulmane_F_char [0] | 1.136 | 97.5/29.25 |  | Vulmane_Male_ASounds |
| 365 | 0x16D | OPTKojanBarbarian | optimizedKojanBarbarian | optimizedKojanBarbarian | (no M; MISSING) / (no F; MISSING) | 1.0 | 90.0/27.0 |  |  |
| 366 | 0x16E | OPTVaranthari | optimizedBarbarian | optimizedBarbarian | UEM_optimizedBarbarian_M_char [0, 1] / UEM_optimizedBarbarian_F_char [0, 1] | 1.088 | 97.5/29.25 | 1 | Barbarian_Male_Q_ASounds |
| 367 | 0x16F | OPTVaranjar | optimizedBarbarian | optimizedBarbarian | UEM_optimizedBarbarian_M_char [0, 1] / UEM_optimizedBarbarian_F_char [0, 1] | 1.088 | 97.5/29.25 |  | Barbarian_Male_T_ASounds |
| 368 | 0x170 | OPTKurashasa | optimizedKura | optimizedKura | UEM_optimizedKura_M_char [0] / UEM_optimizedKura_F_char [0] | 1.151 | 97.5/29.25 |  | Kurashasa_Male_ASounds |
| 369 | 0x171 | CraftingDungeon | craftingDungeon |  | UEM_craftingDungeon_M_char [0] | 1.0 | 60.0/75.0 |  |  |
| 370 | 0x172 | WillowispFlyer | willowisp |  | UEM_willowisp_M_char [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 90, 91, 92, 93, 94] | 1.0 | 100.0/30.0 |  | WillowispSounds |
| 371 | 0x173 | PlayerMetalGolem | golemMetal |  | UEM_golemMetal_M_char [0, 1, 2, 11, 20, 21, 99] | 2.24 | 150.0/50.0 |  | MetalGolemSounds |
| 372 | 0x174 | WyrmGround | wyrm |  | UEM_wyrm_M_char [0, 10, 20, 30, 31, 40, 50, 60, 70, 80, 90, 95, 96, 97, 98, 99, 100] | 2.0 | 200.0/50.0 |  | WyrmSounds |
| 373 | 0x175 | ChasmLizard | lizardChasm |  | UEM_lizardChasm_M_char [0] | 1.0 | 30.0/50.0 |  | KomodoDragonSounds |
| 374 | 0x176 | IODWisp | IODWisp |  | UEM_IODWisp_M_char [0, 1, 4, 7, 10, 13, 21, 35, 37] | 1.0 | 100.0/30.0 |  | WillowispSounds |
| 375 | 0x177 | IODInvisibleMan | optimizedHuman | optimizedHuman | UEM_optimizedHuman_M_char [0, 1, 2, 3, 10, 20, 30, 40, 86, 90, 91, 92, 93, 100] / UEM_optimizedHuman_F_char [0, 1, 2, 3, 90, 91, 92, 93] | 1.0 | 90.0/27.0 | 0 |  |
| 376 | 0x178 | BlockingIODWisp | IODWisp |  | UEM_IODWisp_M_char [0, 1, 4, 7, 10, 13, 21, 35, 37] | 1.0 | 208.0/82.8 |  | WillowispSounds |
| 377 | 0x179 | Angel | AngelPantheon | AngelPantheon | (no M; falls back to angelpantheon_f_char [0, 1, 10, 11, 12, 13]) / UEM_AngelPantheon_F_char [0, 1, 10, 11, 12, 13] | 1.0 | 115.0/40.0 |  | FairyQueenSounds |
| 378 | 0x17A | Snowman | Snowman | Snowman | UEM_Snowman_M_char [0, 1, 2] / (no F; falls back to snowman_m_char [0, 1, 2]) | 1.0 | 80.0/40.0 |  | ElementalEarthSounds |
| 379 | 0x17B | Narcanos | Narcanos |  | UEM_Narcanos_M_char [0] | 3.0 | 250.0/100.0 |  | GiantSounds |
| 380 | 0x17C | Cannon | ParticleCannon | ParticleCannon | UEM_ParticleCannon_M_char [0] / (no F; falls back to particlecannon_m_char [0]) | 1.0 | 115.0/40.0 |  |  |
| 381 | 0x17D | Gharuz | Gharuz | Gharuz | UEM_Gharuz_M_char [0] / (no F; falls back to gharuz_m_char [0]) | 1.0 | 135.0/40.0 |  | BehemothSounds |
| 382 | 0x17E | TargetDummy | targetDummy | targetDummy | UEM_targetDummy_M_char [0] / (no F; falls back to targetdummy_m_char [0]) | 1.0 | 110.0/30.0 |  |  |

Notes: mesh/package names are case-insensitive. Races marked MISSING have no UEM package in Assets and will fail to render: HalfOrc 11, KojanBarbarian 19, HorseDraft 161, TurtleDragonSea 254, FishBass 320, FishGar 321, NPC/OPT HalfOrc/KojanBarbarian. Ids 129 and 135-141 are unassigned and render as mouseman.

## Obstacles (2026-10-13)

NPCs steer around rocks, trees, walls and tents. `server/obstacles.py` reads the chunk's collidable static meshes from the client files: StaticMeshActors in `Assets/Maps/<chunk>.vgr` and the prefabs that CompoundObjects place (`Assets/Archives/binaryprefabs.sgo`), each sized by its StaticMesh bounding box in `Assets/Meshes/*.usx`. The result is a list of circles `(x, y, radius, z_bottom, z_top)` (about 2,650 for chunk_n19_12, built in about 0.4 s on first use). `combat.steer` tries the straight step and then turns of ±30° to ±120°; an NPC whose every way is blocked stands still. Verified by simulation on chunk_n19_12: an NPC walking at MartokRock006 goes around it. There are no obstacles within about 3,000 units of the Ranger camp, so nothing changes there. Terrain DecoLayers (scattered rocks drawn on the terrain) are not obstacles yet. See the module docstring for the file format details and limitations.
