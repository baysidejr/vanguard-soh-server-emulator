"""In-game smoke test (Windows): start the emulator, start the client, enter the world with
the character selected on the character-select screen, type a list of chat commands, then
check the server and client logs for errors.

    python tools/smoke_test.py            # from the repository root (the client install)
    python tools/smoke_test.py --keep     # leave the client and server running afterwards

Prints PASS or FAIL with the problems found; the exit code is 0 on PASS. It closes any
running VGClient.exe and emulator first. Uses only the Python standard library.
"""
import argparse
import ctypes
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server")
BIN = os.path.join(ROOT, "bin")
LOG = os.path.join(SERVER, "smoke_log.txt")
CLIENT_LOG = os.path.join(BIN, "Logs", "VGClient.log")

# Commands typed in game; each should be answered without an error in the logs.
COMMANDS = ["/who", "/played", "/time", "/loc", "/random 100", "/afk", "/afk", "/lfg", "/lfg",
            "/showfactions", "/sit", "/stand", "/decksave 1", "/deckload 1", "/targetself",
            "/forcecombatstance on", "/forcecombatstance off", "/claim", "Hello from the smoke test",
            "/walk", "/run", "/hidehood", "/hidehood", "/hidecloak", "/hidecloak", "/cleartargets", "/cancelability",
            "/lockouttimerlist", "/lockoutdecline", "/citystatus", "/inspect Nobody", "/readycheck",
            "/itemlinkrequest <item=1:1::0:0:0:0:0:x>Copper Ore</link>",
            "/reloadui",
            # dev commands that leave no lasting change on the character
            "!mount 1000", "!mount 0", "!cc stun 1", "!hide", "!hide", "!plot 101",
            # 2026-10-15 features: a crafting session at the camp forge opened and cancelled,
            # a wound set and healed, the builder's mob list, Sprint, the faction lists.
            "!target Camp Forge", "!cev 0xfa", "!cev 0xfe 5001 0", "!cev 0xfd",
            "!wound 2 1", "!wound 2 0", "!mobs bear", "!use Sprint", "!ui Character"]

# Server log lines that mean something went wrong.
SERVER_PROBLEMS = re.compile(r"Traceback|!!! error in|>>> handler error|malformed message")
# Client log lines that mean a message from us was dropped or broken.
CLIENT_PROBLEMS = re.compile(r"Received unhandled message|Critical", re.I)

user32 = ctypes.windll.user32
KEYUP, UNICODE = 0x2, 0x4


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def send_key(vk=0, scan=0, flags=0):
    inp = INPUT(type=1)
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def press(vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    send_key(vk, scan, 0)
    time.sleep(0.05)
    send_key(vk, scan, KEYUP)
    time.sleep(0.05)


def type_text(text):
    for ch in text:
        send_key(0, ord(ch), UNICODE)
        send_key(0, ord(ch), UNICODE | KEYUP)
        time.sleep(0.01)


def client_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value.startswith("Vanguard: Saga of Heroes") and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def focus():
    hwnd = client_window()
    if hwnd:
        user32.keybd_event(0x12, 0, 0, 0)       # an Alt tap lets SetForegroundWindow work
        user32.keybd_event(0x12, 0, 2, 0)
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    return hwnd


def say(text):
    focus()
    press(0x0D)                                  # open the chat line
    time.sleep(0.2)
    type_text(text)
    time.sleep(0.1)
    press(0x0D)


def wait_for(pattern, timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with open(LOG, encoding="utf-8", errors="replace") as f:
                if re.search(pattern, f.read()):
                    return True
        except OSError:
            pass
        time.sleep(1)
    return False


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", "VGClient.exe"], capture_output=True)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object "
                    "{ $_.CommandLine -like '*login_stub.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep", action="store_true", help="leave the client and server running")
    ap.add_argument("--data-dir", help="run the server on this saved-data folder (default: a scratch copy of "
                                       "server/vanguard.db, so the real save is never changed)")
    opts = ap.parse_args()
    kill_all()
    time.sleep(1)
    client_log_start = os.path.getsize(CLIENT_LOG) if os.path.exists(CLIENT_LOG) else 0
    with open(LOG, "w", encoding="utf-8") as out:
        data = opts.data_dir
        if not data:
            import tempfile
            sys.path.insert(0, SERVER)
            import storage
            data = tempfile.mkdtemp(prefix="vgemu-smoke-")
            storage.scratch_copy(SERVER, data)
        server = subprocess.Popen([sys.executable, "-u", "login_stub.py", "--quiet-packets", "--dev-commands",
                                   "--data-dir", data], cwd=SERVER,
                                  stdout=out, stderr=subprocess.STDOUT)
    time.sleep(2)
    subprocess.Popen([os.path.join(BIN, "VGClient.exe"), "--sessionid=12345678"], cwd=BIN)
    problems = []
    if not wait_for(r"character record 0x19", 180):
        problems.append("the character-select list never arrived")
    else:
        time.sleep(6)
        focus()
        press(0x0D)                              # Play with the selected character
        if not wait_for(r"control <- 'JOIN'", 120):
            problems.append("the client never joined the world")
        else:
            time.sleep(12)
            for c in COMMANDS:
                say(c)
                time.sleep(1.5)
            time.sleep(3)
    with open(LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            if SERVER_PROBLEMS.search(line):
                problems.append("server: " + line.strip())
    if os.path.exists(CLIENT_LOG):
        with open(CLIENT_LOG, encoding="utf-8", errors="replace") as f:
            f.seek(client_log_start)
            for line in f:
                if CLIENT_PROBLEMS.search(line):
                    problems.append("client: " + line.strip()[-160:])
    if server.poll() is not None:
        problems.append(f"the server exited with code {server.returncode}")
    if not opts.keep:
        kill_all()
    if problems:
        print("FAIL")
        for p in dict.fromkeys(problems):
            print("  " + p)
        print(f"Server log: {LOG}")
        return 1
    print(f"PASS: logged in, entered the world and ran {len(COMMANDS)} commands with no errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
