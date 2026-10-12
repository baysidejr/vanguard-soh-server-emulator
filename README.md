# Vanguard: Saga of Heroes — Server Emulator

An open-source server emulator for **Vanguard: Saga of Heroes** (SOE, shut down in July 2014), built by reverse-engineering the original game client.

> **No game files are included.** You need your own copy of the Vanguard client (version 1.324.1.139565). This repository contains only original emulator code and protocol notes.

## Status

The unmodified client, talking only to this emulator:

- [x] Logs into the login server
- [x] Sees the server list ("Stub World")
- [x] Lists, creates, customizes and deletes characters, with 3D previews
- [x] Connects to the world server, then to a zone server after **Play**
- [x] Completes the Unreal Engine 2 handshake (HELLO → CHALLENGE → LOGIN → WELCOME → JOIN) and loads a level
- [x] Enters the 3D world: loads the character's chunk (with neighbours) and takes control of a replicated PlayerController at a PlayerStart
- [x] Shows the in-game HUD (vitals, chat, minimap) and a message of the day
- [x] The character is visible and walks around; the server tracks its position
- [x] Character window: name, level, race and class
- [x] Attributes (Strength...), hit points, endurance and energy; full HUD bars
- [x] Skills list (weapon, combat, perception... groups)
- [x] Inventory: items in the bag and coins ([docs/INVENTORY.md](docs/INVENTORY.md))
- [ ] Full appearance (gender, face, gear), NPCs, other players

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for everything decoded so far.

## Requirements

- Python 3.10+ (standard library only)
- A Vanguard: Saga of Heroes client install

## Running

1. Put this repository's files in the root of the client install (next to `bin/`).
2. Set `bin/loginserver.txt` to `127.0.0.1`.
3. Start the emulator:
   ```
   cd server
   python login_stub.py
   ```
   It listens on UDP 10101 (login), 10100 (world) and 10102 (zone). It reads package GUIDs from the client's `UnrealScript/` and `Assets/Maps/` folders (nothing is copied or shipped).
4. In another terminal, start the client directly (this skips the old VGOEmulator launcher):
   ```
   cd bin
   .\VGClient.exe --sessionid=12345678
   ```

Characters are saved to `server/characters.json`. The emulator prints every packet it receives, decoded where the format is known.

## How it was built

Each message format was found by static analysis of `VGClient.exe` (Ghidra, via REA), then verified by running the real client against the emulator. Function addresses in the notes refer to Ghidra's names for that exact client build.

## License

[GNU Affero General Public License v3.0](LICENSE). If you run a modified version of this emulator as a public server, you must publish your changes.

*Vanguard: Saga of Heroes is a trademark of its respective owners. This project is not affiliated with or endorsed by them.*
