# Chat, channels, emotes and socials (VGClient.exe static analysis)

> **Verified live with two clients (2026-10-12):** shout (`You shout, "…"` / `Justins shouts, "…"`), tell (`To [Ranger]: …` / `From [Justins]: …`), OOC (`[OOC][Justins]: …`), group chat and the "You're not in a group." error, `/emote` and `/wave` (social ability 400151 via 0x3d1 plus an emote line). Implemented in `server/chat.py` and `login_stub.world_chat`.


[O] = read in code/data, [I] = inferred. Wire types follow docs/ZONE_MESSAGES.md
(wstr = UTF-16LE NUL-terminated, no length prefix; bool8 = 1 byte; i16 = 2 bytes).

## 1. World message type 6 = "chat/command channel" envelope

- [O] World dispatcher `FUN_00d9aa60` sends type 6 to listener vtable +0x20. The listener vtable is at
  `0x10cd170` (RTTI COL at 0x10cd16c): +0x10 type 2 = `FUN_006ed950` -> `FUN_0062aaf0` (normal world events),
  +0x20 type 6 = `FUN_006edb30` -> **`FUN_0041b910`** (chat handler).
- [O] Frame (`FUN_006ebbe0` + `FUN_0041a5b0`): `u16 6 | u32 event id | u32 data length | data`.
  It has the same shape as the type-2 envelope (`event_message`), with 6 in the first field.
- [O] C->S: the client sends every server-side slash command as **type 6, event 0x14**, with data = a wstr command
  line (`FUN_005fc6a0` / `FUN_00409240(0x14, wstr, bytelen)` -> `FUN_006ee6d0`). Formats seen in code:
  `tell "%s" %s` (FUN_0060e790), `gsay %s`, `rsay %s`, `mindsay %s`, `regionsay %s`, `guildsay %s`,
  `"<channel>" <text>` (numbered channel `/N`, FUN_004a0930), `join "<channel>"` (autojoin, FUN_004a0fd0).
  The /ooc and /regionsay commands both become `regionsay`.

### S->C type-6 events (all handled in FUN_0041b910 / pre-filter FUN_004a1e00) [O]

| event | class | payload (wire order) | effect |
|---|---|---|---|
| 0x0e | MsgSingleShort | i16 code | chat error text (FUN_00419f10): 1 GenericSuccess, 2 GenericFail, 3 InsufficientPriviledge, 0x1a NoGuild, 0x1d CantTellYourself, 0x1e YouMayNotSendTells, 0x1f ThatPersonNotOnline, 0x20/0x21/0x22 nickname, 0x23 AwayMessageTooLong, 0x24 NoLongerAway, 0x25 InvalidChannel, 0x26 InvalidChannelOrPlayer, 0x27 IncorrectPassword, 0x28 NoGroup, 0x29 NoMindSay, 0x2a ChatThrottled, 0x2b NotAcceptingTrialTells |
| **0x0f** | MsgTwoStringsAndInt | wstr text, wstr speaker, i32 chat type | **incoming chat line** (formatted by FUN_0041af60, echo=0) |
| 0x10 | MsgStringAndInt | wstr text, i32 chat type | raw line, no format (system text in that chat type's colour/tab) |
| **0x11** | MsgStringAndInt | wstr text, i32 chat type | **sender echo without receiver** (FUN_0041b5a0): "You say/shout", "To [Group]: ..." |
| **0x12** | MsgTwoStringsAndInt | wstr text, wstr receiver, i32 chat type | **sender echo with receiver** (FUN_0041af60, echo=1): tells, channel say |
| **0x13** | MsgThreeStringsAndInt | wstr text, wstr speaker, wstr channel name, i32 chat type | **chat-channel line** "ChannelSay" = `[channel][speaker]: text` |
| 0x317 | MsgStringAndBool | wstr channel name, bool8 regional | channel joined: adds to the /N list (FUN_004a1bc0). regional=1 -> number 1 (region), or 2 if name starts with "auction". Otherwise first free number from 3 to 9 |
| 0x318 | MsgSendSingleSGOString | wstr channel name | channel left (FUN_004a16d0) |
| 0x319 | (none) | - | client sends `join "<name>"` for each autojoin entry (FUN_004a0fd0; the default autojoin string in the binary is "regionsay,auction") [O]/[I] |
| 0x5a0 | MsgStringAndTwoInts | wstr, i32, i32 | social-window channel list entry (FUN_00646b60/FUN_006497c0) [I] |
| 0x551 | MsgStringAndByte | wstr, u8 | red on-screen alert with `<displayTicks> 5000` (raid alert?) [I] |

The client checks the speaker of 0x0f and 0x13 against its ignore list (FUN_0057f7d0) and runs the text through the
profanity filter. Text that starts with `<spam>` is shown but not logged. For 0x0f it plays a sound: chat type 0x0f plays
"UISounds.Tell1" and 0x10 plays "UISounds.Tell5". Both also add the speaker to the /reply list (FUN_005f1f80).

### Chat type id -> format (VGClient.int [Command]) [O]
Incoming (0x0f, FUN_0041af60). %1 = speaker (2nd wstr) and %2 = text (1st wstr):

| id | key | text |
|---|---|---|
| 3 | Say | `<speaker> says, "text"` |
| 4 | **Shout** | `<speaker> shouts, "text"` |
| 5 | Emote | `<speaker> text` |
| 8 | **GroupSay** | `[Group][speaker]: text` |
| 9 | RaidSay | `[Raid][speaker]: text` |
| 0x0b / 0x0c / 0x0d | GuildSay / GuildSayLeader / GuildSayOfficer | `[Guild][speaker]: text` |
| 0x0f | **Tell** | `From [speaker]: text` (+ Tell1 sound, reply target) |
| 0x10 | GMTell | `From [speaker (GM)]: text` |
| 0x11 | Mindsay | `[Union of the Minds][speaker]: text` |
| 0x27 | Broadcast | `<speaker> broadcasts, "text"` |
| 0x4d | (raw) | text only |
| 0x5d | LFG | `[LFG][speaker]: text` |
| other | UnknownMsg | `[???][speaker]: text` |

Echo 0x11 (FUN_0041b5a0), %1 = text: 3 SayEcho "You say", 4 ShoutEcho "You shout", 8 GroupSayEcho "To [Group]",
9 RaidSayEcho, 0x0b-0x0d GuildSayEcho, 0x11 MindsayEcho, 0x27 BroadcastEcho, 0x46 PetitionEcho, 0x4d raw,
0x5d LFGEcho, other "To [???]: text".
Echo 0x12 (FUN_0041af60 echo=1), %1 = receiver and %2 = text: 0x0f/0x10 TellEcho `To [receiver]: text`,
**0x3a ChannelSayEcho `To [channel]: text`**, other `To [??? (receiver)]: text`.
Chat type **0x3a** is the custom/region chat-channel type. The client uses it for "List of channels"
(FUN_004a0c20) [O]. Region/OOC lines therefore use event 0x13 with chat type 0x3a [I].

### Why zone 0x0f shows "[???]"
[O] Zone event 0x0f is handled by FUN_00621d60. It only knows 3 (Say) and 5 (Emote) and maps every other type to
UnknownMsg. The full table is only in the **world type-6** handler. There is no channel-name table to send first:
names are literal ("Group", "Raid"...) or come in the 0x13 payload.

## 2. Emotes and socials (zone)
- [O] `/emote` (exec FUN_00612700, table entry 0x13f093c "/emote") sends zone 0x314 MsgSendSingleSGOString {wstr}.
  It does **not** echo locally.
  -> Server: zone event **0x0f {wstr text, wstr speaker, i32 5}** to the sender and to nearby players.
  Result: `<pcname>Name</pcname> text`.
- [O] `/social` (FUN_006127e0, "/social") -> FUN_004d08d0 sends zone 0x313 MsgEntityIDAndTwoStrings {eid64 target (-1 if none),
  wstr social name e.g. "WAVE", wstr extra (usually empty)} (schema FUN_004d0540).
- [O] `UEMFXMeshInstance::PlaySocial` (FUN_00923de0) is an empty stub. Socials are **abilities** in
  `Assets/Abilities/SOCIAL_ABILITIES.aby`: export `SOCIAL_ABILITIES_<id>` with tag `SOCIAL_<NAME>_<id>`
  (all 159 named tags match their export id; for example WAVE = **400151**, WAVE_OVERHEAD 400152, BOW 400014,
  DANCE_1 400041). Every phase 0-6 plays the same caster Action (e.g. SOC_ANIM_WAVE_400157) and has no target Action.
  -> Server: zone **0x3d1 MsgDisplayAbility** (`combat.display_ability(caster=player eid, target=target or NO_ENTITY,
  visual_id=400151, phase=2)`) to the sender and to nearby players. The id range 400001-409999 maps to SOCIAL_ in
  FUN_007f3640 [O]. The client has no social text strings, so a line such as "waves." or "waves at X." must be
  composed by the server and sent as zone 0x0f type 5 [I].
- Name -> id map: parse SOCIAL_ABILITIES.aby (scratchpad soc.py / socmap.txt) or hardcode the table.
  400161 = SOCIAL_IDLEBREAK and 400162 = SOCIAL_OVERHEAD_SWING have no number in their tag.

## 3. Server recipe
```
def chat6(event, data): return struct.pack("<HII", 6, event, len(data)) + data
W = lambda s: (s + "\0").encode("utf-16-le")
line      = chat6(0x0F, W(text) + W(speaker) + struct.pack("<i", kind))        # receivers
echo      = chat6(0x11, W(text) + struct.pack("<i", kind))                     # sender, no receiver
echo_to   = chat6(0x12, W(text) + W(receiver) + struct.pack("<i", kind))       # sender, tells/channels
chan_line = chat6(0x13, W(text) + W(speaker) + W(chan) + struct.pack("<i", 0x3A))
error     = chat6(0x0E, struct.pack("<h", code))                               # e.g. 0x1f not online
```
Parse world type 6 event 0x14 wstr:
- `shout T` -> line(4) to all and echo(4) to the sender.
- `tell "N" T` -> line(0x0f) to N and echo_to(N, 0x0f) to the sender. If N is offline, send error 0x1f. If N is the sender, send 0x1d.
- `gsay T` -> line(8) to group members and echo(8) to the sender (if there is no group, error 0x28).
- `rsay` -> 9. `guildsay` -> 0x0b. `mindsay` -> 0x11.
- `regionsay T` -> chan_line(chan="OOC" or a region name) to all and echo_to(chan, 0x3a) to the sender.
- `"Chan" T` -> same as regionsay for that channel.
- `join "X"` -> 0x317 {W(X), bool}.
Optionally send 0x319 after world login so the client auto-joins its channels.
[I] The echo behaviour is inferred from the dedicated echo handlers. Check live that the client does not echo these commands itself.

## Key addresses
FUN_00d9aa60 world dispatcher; FUN_006edb30 type-6 entry; FUN_0041b910 chat handler; FUN_004a1e00 channel pre-filter;
FUN_0041af60 line/echo-with-receiver formatter; FUN_0041b5a0 echo formatter; FUN_00419f10 error codes;
FUN_00621d60 zone 0x0f formatter (3/5 only); FUN_005fc6a0 C->S command send; FUN_0060e790 tell builder;
FUN_004a0930 /N; FUN_004a0c20 list channels; FUN_004a1bc0 add channel; FUN_00612700 /emote (0x314);
FUN_006127e0 /social -> FUN_004d08d0 (0x313); FUN_007f3640 ability id -> package.

## Item and player links (item link answer verified live 2026-10-14)

Chat text is markup. The tag table (FUN_00cb2e10) registers `item` (type 0x12), `/item` and `/link` (0x14, closing tags) and `pcname` (0x13), besides `color`, `size`, `align`, `indent`, `nl`, `image`, `highlight`, `tab`, `key`, `gamevar`/`gv` and `visibilitygamevar`/`vgv`.

- The client writes item links itself as `<item=%i:%i::%i:%i:%i:%i:%i:%s>%s</link>` (FUN_00cde960): the item's template id first, then numbers from the item (FUN_00513be0) and its name. It does this for its own "You loot ..." lines (FUN_00522920) and when you link an item into chat (FUN_00692820).
- Clicking an item link in the chat window runs `/itemlinkrequest <link text>` (FUN_00c7c590), which sends zone event **0x158 {wstr}**. Clicking a `<pcname>` runs `/tell <name> ` (left) or `/showpccontextwindow <name>` (right).
- The answer is **s2c 0x158** MsgSingleItemInfo: the item's full inventory record (FUN_005de090 builds the item with FUN_00516610 and opens the examine popup, FUN_0068e220). The server finds the item by the name inside the link, else by the template id (the first number), and sends its record. Verified live 2026-10-14: `/itemlinkrequest <item=1:1::0:0:0:0:0:x>Copper Ore</link>` pops up the Copper Ore tooltip (Crafting Resource, Required Level 1 Crafting). Unknown items get no answer.
