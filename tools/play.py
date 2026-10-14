"""Launcher: log in with a username and password, then start the game client.

Like the original SOE launcher, it checks the account with the server and starts the client with
the one-time session token it gets back (`VGClient.exe --sessionid=<token>`). Run from the
repository root (the client install):

    python tools/play.py                      # asks for username and password
    python tools/play.py --register           # create an account first (if the server allows it)
    python tools/play.py --server 192.168.1.20

The server's launcher endpoint is HTTP on port 10180 (login_stub.py --launcher-port). The game
client itself connects to the login server named in bin/loginserver.txt. Uses only the standard
library.
"""
import argparse
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")


def post(url, username, password):
    req = urllib.request.Request(url, data=json.dumps({"username": username, "password": password}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}")
        except ValueError:
            return {"error": f"HTTP {e.code}"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", default="127.0.0.1", help="the server's address")
    ap.add_argument("--port", type=int, default=10180, help="the server's launcher port")
    ap.add_argument("--register", action="store_true", help="create the account first")
    ap.add_argument("--username")
    ap.add_argument("--no-start", action="store_true", help="only print the session token")
    a = ap.parse_args(argv)
    username = a.username or input("Username: ").strip()
    password = os.environ.get("VG_PASSWORD") or getpass.getpass("Password: ")
    base = f"http://{a.server}:{a.port}"
    try:
        reply = post(base + ("/register" if a.register else "/login"), username, password)
    except (OSError, urllib.error.URLError) as e:
        print(f"Can't reach the server at {base}: {e}")
        return 1
    token = reply.get("session")
    if not token:
        print(reply.get("error", "Login failed."))
        return 1
    if a.no_start:
        print(token)
        return 0
    exe = os.path.join(BIN, "VGClient.exe")
    print("Logged in; starting the game.")
    subprocess.Popen([exe, f"--sessionid={token}"], cwd=BIN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
