# Running a server for other people

How to run the emulator for players on other machines (a LAN party or the internet). Everything
here is in the repository; nothing extra needs installing besides Python 3.10+ and, for HTTPS,
a certificate.

## Ports

| Port | Protocol | What |
|---|---|---|
| 10101 | UDP | login server (`--port`) |
| 10100 | UDP | world server (`--world-port`) |
| 10102 | UDP | zone server (`--zone-port`) |
| 10180 | TCP | launcher login, HTTP or HTTPS (`--launcher-port`, 0 turns it off) |

Open (or forward) all four on the server's firewall / router.

## Starting the server

```
cd server
python login_stub.py --quiet-packets --world-address <public address> \
    --launcher-cert server.crt --launcher-key server.key \
    --data-dir D:/vanguard-data
```

- `--world-address` is the address the server tells clients to connect to for the world and zone
  servers. On a LAN use the machine's LAN address; on the internet its public address (or name).
  With the default `127.0.0.1` only clients on the same PC can play.
  (Checked 2026-10-14 with the PC's LAN address in both `--world-address` and the client's
  `bin/loginserver.txt`: login, world and zone all connected over it and the character spawned.)
- `--launcher-cert` / `--launcher-key` serve the launcher over HTTPS, so passwords are encrypted.
  A self-signed certificate works (players then pass it with `--cafile`):
  `openssl req -x509 -newkey rsa:2048 -nodes -keyout server.key -out server.crt -days 365 -subj "/CN=myserver"`.
  Key and certificate files are never committed.
- `--data-dir` keeps the database (`vanguard.db`), its backups and the bug / player reports in a
  folder of your choice (default: `server/`).
  `server/accounts.py` and `server/storage.py` take the same `--data-dir <folder>` as their first
  option (`python server/accounts.py --data-dir D:/vanguard-data list`).
- `--quiet-packets` keeps the log readable (and the server faster).
- `--allow-registration` lets players create their own accounts from the launcher.

Never use these on a public server:

- `--dev-commands`: every player could use the `!` commands (`!give`, `!tp`, `!kill`, ...).
- `--anonymous-zone`: lets a connection enter the world without logging in.

## Accounts

On its first start the server creates a `dev` account (password printed once) that owns the
characters already in the database and the test launcher tokens `12345678` and `22222222`.
Anyone who knows those tokens can log in as `dev`, so on a public server remove them:

```
python server/accounts.py untoken 12345678
python server/accounts.py untoken 22222222
```

Then make accounts (`python server/accounts.py create <name> <password>`), or open registration.
`python server/accounts.py list | suspend <name> | unsuspend <name> | password <name> <new>`
manage them. Make someone a GM with `python server/storage.py set <character> access_level 255`
(while the character is offline); GMs get the client's own `/chunk`, `/gotoplayer`,
`/summonplayer`, `/summongroup` and `/hideme`.

## Players

Each player needs their own Vanguard client (version 1.324.1.139565) with this repository's
`tools/play.py`, and:

1. `bin/loginserver.txt` set to the server's address.
2. `python tools/play.py --server <address> --https` (add `--cafile server.crt` for a self-signed
   certificate; `--register` to create an account if registration is open).

## While it runs

- Type `who`, `announce <text>`, `kick <name>`, `backup` or `stop` in the server's window.
- The database is copied to `<data folder>/backups/` at start and every 6 hours
  (`--backup-hours`), keeping the last 10. `python server/storage.py export` writes everything out
  as JSON.
- Stop with `stop`, Ctrl+C or a service stop: every player is saved and disconnected.
- `audit.log` next to the database records every trade, mail with coins or an item, broker
  sale and dev `!give` (one JSON line each: who, to whom, what): the place to look when a player
  reports a scam or a duplication.
- Every 10 minutes the log gets a `status` line: players online, connections, packets a second,
  how busy the server loop was, resends.
- Lines starting with `!!!` in the log are worth a look: handler errors (the server keeps
  running), `!!! load` (it is falling behind), `!!! network` (packets lost), failed backups.

## Abuse limits

- A connection may send about 300 messages a second (bursts to 600); more is dropped, and one
  that stays over the limit for 10 seconds is disconnected (`!!! flood` in the log). Chat (say,
  shout, tell...) is limited to 5 lines a second ("You are sending messages too quickly.").
- Login attempts: 5 failed logins per address per 5 minutes, counting both the launcher's
  password check and the game's own login (so launcher tokens can't be guessed either).
- A character logged in twice keeps only the newer connection.
- Movement: a report that jumps more than 2000 units without a server teleport, or averages more
  than riding speed (with room for lag) over 2 seconds, is logged as `MOVEMENT WARNING`. With
  `--enforce-movement` the player is also moved back to their last good position (a speed or
  teleport hack gets nowhere). Normal walking, riding and server teleports never triggered it in
  testing, but it is off by default.

## How many players

One server process handles one shard. Measured with `tools/loadtest.py` on a desktop PC
(docs/TESTING.md): about 200 players moving at the same time when spread over a chunk, about 150
all in one spot, with pings around 10 ms. Logging in hundreds of players within seconds takes
longer than that (each login opens every nearby player and NPC for the newcomer).

## Known gaps

All game data (items, mobs, quests, abilities, rewards) is placeholder content; see
docs/CONTENT_EDITOR.md.
