"""Drive the real game client step by step for hand-run checks (Windows), on a scratch save.

    python tools/client_ui.py start [--free-slot NAME]   # scratch copy of the save, dev server, client
    python tools/client_ui.py play                       # Play the character select's choice; waits for WELCOME
    python tools/client_ui.py say "/who"                 # type a chat line or command
    python tools/client_ui.py click X Y                  # left-click at window pixel X, Y (as in the screenshot)
    python tools/client_ui.py rclick X Y                 # right-click (altars, merchants, items)
    python tools/client_ui.py key 0x1B                   # press a virtual key
    python tools/client_ui.py type TEXT                  # type text into the focused field
    python tools/client_ui.py shot [FILE]                # screenshot of the game window (PNG)
    python tools/client_ui.py stop                       # close client and server, delete the scratch copy

Every action except stop ends with a screenshot (default: client_ui.png in the system temp folder),
whose pixels match the X, Y of click/rclick. The server runs with --dev-commands on a read-only
copy of server/vanguard.db in a temp folder, so the real save is never touched; --free-slot removes
one character from that copy so the create screen has a slot. The client picks the last played
character on the select screen. Only run it when nobody is using the PC (it takes the keyboard and
mouse). From Git Bash, run `say` with MSYS_NO_PATHCONV=1, or a leading "/" (as in "/who") is turned
into a Windows path before Python sees it. Uses only the Python standard library (ctypes, PowerShell
for the PNG).
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server")
SCRATCH = os.path.join(tempfile.gettempdir(), "vgemu-client-ui")
LOG = os.path.join(SERVER, "client_ui_log.txt")
DEFAULT_SHOT = os.path.join(tempfile.gettempdir(), "client_ui.png")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, SERVER)
import smoke_test  # noqa: E402
import storage  # noqa: E402

u32 = ctypes.windll.user32 if os.name == "nt" else None


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def window_rect():
    r = RECT()
    u32.GetWindowRect(smoke_test.client_window(), ctypes.byref(r))
    return r.l, r.t, r.r, r.b


def shot(out=DEFAULT_SHOT):
    """PNG of the game window; its pixels are the X, Y that click/rclick take."""
    l, t, r, b = window_rect()
    ps = (f"Add-Type -AssemblyName System.Drawing; $bmp = New-Object System.Drawing.Bitmap {r - l}, {b - t}; "
          f"$g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen({l}, {t}, 0, 0, $bmp.Size); "
          f"$bmp.Save('{out}')")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(out)


def _mouse(x, y, down, up):
    l, t, _r, _b = window_rect()
    smoke_test.focus()
    time.sleep(0.3)
    u32.SetCursorPos(l + x, t + y)
    time.sleep(0.2)
    u32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.08)
    u32.mouse_event(up, 0, 0, 0, 0)


def _log():
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def start(free_slot=None):
    shutil.rmtree(SCRATCH, ignore_errors=True)
    storage.scratch_copy(SERVER, SCRATCH)
    if free_slot:
        path = os.path.join(SCRATCH, "characters.json")
        storage.write_characters(path, [c for c in storage.read_characters(path) if c.get("first") != free_slot])
    smoke_test.kill_all()
    time.sleep(1)
    detached = 0x00000008            # DETACHED_PROCESS: both outlive this command
    subprocess.Popen([sys.executable, "-u", "login_stub.py", "--quiet-packets", "--dev-commands", "--data-dir", SCRATCH],
                     cwd=SERVER, stdout=open(LOG, "w", encoding="utf-8"), stderr=subprocess.STDOUT,
                     creationflags=detached)
    time.sleep(3)
    subprocess.Popen([os.path.join(ROOT, "bin", "VGClient.exe"), "--sessionid=12345678"],
                     cwd=os.path.join(ROOT, "bin"), creationflags=detached)
    end = time.time() + 180
    while time.time() < end and "character record 0x19" not in _log():
        time.sleep(2)
    time.sleep(8)


def play():
    smoke_test.focus()
    smoke_test.press(0x0D)
    end = time.time() + 120
    while time.time() < end and "WELCOME" not in _log():
        time.sleep(2)
    time.sleep(20)          # the world streams in after WELCOME; chat typed earlier is lost


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "stop":
        smoke_test.kill_all()
        time.sleep(2)
        shutil.rmtree(SCRATCH, ignore_errors=True)
        return 0
    out = DEFAULT_SHOT
    if cmd == "start":
        start(args[args.index("--free-slot") + 1] if "--free-slot" in args else None)
    elif cmd == "play":
        play()
    elif cmd == "say":
        if len(args[0]) > 2 and args[0][1] == ":" and "/Git/" in args[0].replace("\\", "/"):
            print("Git Bash turned the leading / into a path; run with MSYS_NO_PATHCONV=1 (see the docstring)")
            return 2
        smoke_test.say(args[0])
        time.sleep(2)
    elif cmd in ("click", "rclick"):
        _mouse(int(args[0]), int(args[1]), *((0x0002, 0x0004) if cmd == "click" else (0x0008, 0x0010)))
        out = args[2] if len(args) > 2 else out
    elif cmd == "key":
        smoke_test.focus()
        smoke_test.press(int(args[0], 0))
        out = args[1] if len(args) > 1 else out
    elif cmd == "type":
        smoke_test.focus()
        smoke_test.type_text(args[0])
        out = args[1] if len(args) > 1 else out
    elif cmd == "shot":
        out = args[0] if args else out
    else:
        print(__doc__)
        return 2
    time.sleep(2.5)
    shot(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
