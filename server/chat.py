"""World-server chat (message type 6; client handler FUN_0041b910). Slash
commands arrive on the world connection as type 6 event 0x14 {wstr command}:
"shout T", 'tell "N" T', "gsay T", "regionsay T". Replies are type 6 too:
  0x0f {wstr text, wstr speaker, i32 type}   incoming line
  0x11 {wstr text, i32 type}                  echo to the sender ("You shout, ...")
  0x12 {wstr text, wstr receiver, i32 type}   echo with a receiver ("To [N]: ...")
  0x13 {wstr text, wstr speaker, wstr channel, i32 type}  channel line
  0x0e {i16 error}                            0x1d can't tell yourself, 0x1f not
                                              online, 0x28 not in a group
(docs/CHAT.md)."""
import struct

SAY, SHOUT, EMOTE, GROUP, TELL, CHANNEL = 3, 4, 5, 8, 0x0F, 0x3A
ERR_TELL_SELF, ERR_NOT_ONLINE, ERR_NO_GROUP = 0x1D, 0x1F, 0x28


def _w(text):
    return (text + "\0").encode("utf-16-le")


def _msg(event, data):
    return struct.pack("<HII", 6, event, len(data)) + data


def line(text, speaker, kind):
    return _msg(0x0F, _w(text) + _w(speaker) + struct.pack("<i", kind))


def echo(text, kind):
    return _msg(0x11, _w(text) + struct.pack("<i", kind))


def echo_to(text, receiver, kind):
    return _msg(0x12, _w(text) + _w(receiver) + struct.pack("<i", kind))


def channel_line(text, speaker, channel):
    return _msg(0x13, _w(text) + _w(speaker) + _w(channel) + struct.pack("<i", CHANNEL))


def error(code):
    return _msg(0x0E, struct.pack("<h", code))


def parse(command):
    """("shout", None, text) / ("tell", name, text) / ("gsay", None, text) /
    ("regionsay", None, text) / (verb, None, rest) for anything else."""
    verb, _, rest = command.partition(" ")
    if verb == "tell" and rest.startswith('"'):
        name, _, text = rest[1:].partition('"')
        return "tell", name, text.strip()
    return verb, None, rest


_socials = {}


def social_ids(client_dir):
    """Social name ("WAVE") -> ability id (400151) from SOCIAL_ABILITIES.aby,
    whose exports are tagged SOCIAL_<NAME>_<id>. Played with zone 0x3d1."""
    if not _socials:
        import class_abilities
        for aid, tag in class_abilities.package_abilities(client_dir, "SOCIAL"):
            name = tag[len("SOCIAL_"):] if tag.startswith("SOCIAL_") else tag
            if name.endswith("_" + str(aid)):
                name = name[:-len(str(aid)) - 1]
            _socials.setdefault(name.upper(), aid)
    return _socials
