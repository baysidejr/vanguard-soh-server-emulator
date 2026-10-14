"""Player accounts: usernames, password hashes and login session keys.

The original game logged in through SOE's launcher: the player typed their Station account and
password there, and the launcher started the client with a session token (`--sessionid`). The
client's first message to the login server, PacketLoginRequest, carries two strings: "SOE_LOGIN"
and that token, or (without the launcher) a username and password.

This server keeps accounts in accounts.json (runtime data, never committed):

    {"accounts": {username (lower case): {"name", "salt", "hash", "iterations", "created"}},
     "launcher_tokens": {token: username}}

Passwords are stored only as salted PBKDF2-SHA256 hashes. launcher_tokens stand in for the
launcher: `python accounts.py token <username> <token>` lets `VGClient.exe --sessionid=<token>`
log in as that account. After a successful login the server issues its own random session key,
which the client hands to the world and zone servers (login event 0x27); those check it.

Command line (run from server/):
    python accounts.py create <username> <password>
    python accounts.py password <username> <new password>
    python accounts.py token <username> <launcher token>
    python accounts.py suspend <username>      (and unsuspend <username>)
    python accounts.py list
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time

import storage

ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")
ITERATIONS = 200_000
LAUNCHER_LOGIN = "SOE_LOGIN"
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
DEV_ACCOUNT = "dev"

# Session keys issued at login: key -> username (in memory; a restart logs everyone out).
SESSIONS = {}
# One-time launch tokens from the launcher endpoint: token -> (username, expiry time).
LAUNCH_TOKENS = {}
LAUNCH_TOKEN_SECONDS = 120
# Failed launcher logins per client address: address -> [times], to slow down password guessing.
FAILURES = {}
MAX_FAILURES, FAILURE_WINDOW = 5, 300


def load():
    try:
        with open(ACCOUNTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("accounts", {})
    data.setdefault("launcher_tokens", {})
    return data


def save(data):
    storage.write_json_atomic(ACCOUNTS_FILE, data)


def _hash(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()


def create(username, password, data=None):
    """Add an account; returns an error string or None."""
    data = data if data is not None else load()
    if not NAME_RE.match(username or ""):
        return "Usernames are 3-32 letters, digits, '_', '.' or '-'."
    if len(password or "") < 6:
        return "Passwords need at least 6 characters."
    key = username.lower()
    if key in data["accounts"]:
        return "That username is taken."
    salt = secrets.token_hex(16)
    data["accounts"][key] = {"name": username, "salt": salt, "hash": _hash(password, salt),
                             "iterations": ITERATIONS, "created": int(time.time())}
    save(data)
    return None


def set_password(username, password, data=None):
    data = data if data is not None else load()
    acc = data["accounts"].get((username or "").lower())
    if acc is None:
        return "No such account."
    if len(password or "") < 6:
        return "Passwords need at least 6 characters."
    acc["salt"] = secrets.token_hex(16)
    acc["iterations"] = ITERATIONS
    acc["hash"] = _hash(password, acc["salt"])
    save(data)
    return None


def set_token(username, token, data=None):
    data = data if data is not None else load()
    if (username or "").lower() not in data["accounts"]:
        return "No such account."
    if len(token or "") < 6:
        return "Tokens need at least 6 characters."
    data["launcher_tokens"][token] = username.lower()
    save(data)
    return None


def set_suspended(username, flag, data=None):
    data = data if data is not None else load()
    acc = data["accounts"].get((username or "").lower())
    if acc is None:
        return "No such account."
    acc["suspended"] = bool(flag)
    save(data)
    return None


def is_suspended(username, data=None):
    data = data if data is not None else load()
    return bool(data["accounts"].get((username or "").lower(), {}).get("suspended"))


def check_password(username, password, data=None):
    """The account's username (lower case) if the password is right, else None."""
    data = data if data is not None else load()
    acc = data["accounts"].get((username or "").lower())
    if acc is None:
        _hash(password or "", "00" * 16)          # same work either way: no username probing by timing
        return None
    good = hmac.compare_digest(_hash(password or "", acc["salt"], acc.get("iterations", ITERATIONS)), acc["hash"])
    return (username or "").lower() if good else None


def login(field1, field2, data=None):
    """PacketLoginRequest -> the account (lower case), or None. field1 "SOE_LOGIN" means field2 is
    a launcher token; otherwise the fields are username and password."""
    data = data if data is not None else load()
    if field1 == LAUNCHER_LOGIN:
        issued = LAUNCH_TOKENS.pop(field2, None)          # one use only
        if issued is not None and issued[1] >= time.time():
            return issued[0]
        return data["launcher_tokens"].get(field2)
    return check_password(field1, field2, data)


def issue_launch_token(username):
    """A one-time token for `VGClient.exe --sessionid=<token>`, valid LAUNCH_TOKEN_SECONDS."""
    token = secrets.token_hex(16)
    LAUNCH_TOKENS[token] = (username, time.time() + LAUNCH_TOKEN_SECONDS)
    return token


def launcher_login(address, username, password, now=None):
    """The launcher's username / password check: (token, None) or (None, error message).
    Too many failures from one address within FAILURE_WINDOW seconds are refused outright."""
    now = time.time() if now is None else now
    recent = [t for t in FAILURES.get(address, []) if now - t < FAILURE_WINDOW]
    if len(recent) >= MAX_FAILURES:
        FAILURES[address] = recent
        return None, "Too many failed logins; wait a few minutes."
    account = check_password(username, password)
    if account is None:
        FAILURES[address] = recent + [now]
        return None, "Wrong username or password."
    FAILURES.pop(address, None)
    return issue_launch_token(account), None


def serve_launcher(host, port, allow_register=False):
    """Start the launcher endpoint (a background thread): POST /login (and POST /register when
    allowed) with a JSON body {"username", "password"} -> {"session": token} or {"error": text}.
    Plain HTTP: put it behind TLS (or keep it on a private network) before exposing it."""
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                username, password = str(body.get("username", "")), str(body.get("password", ""))
            except (ValueError, AttributeError):
                return self.reply(400, {"error": "Bad request."})
            if self.path == "/register" and allow_register:
                err = create(username, password)
                if err:
                    return self.reply(400, {"error": err})
            elif self.path not in ("/login", "/register"):
                return self.reply(404, {"error": "Not found."})
            elif self.path == "/register":
                return self.reply(403, {"error": "Registration is closed on this server."})
            token, err = launcher_login(self.client_address[0], username, password)
            self.reply(200 if token else 403, {"session": token} if token else {"error": err})

        def reply(self, code, obj):
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            print(f"  launcher {self.client_address[0]}: {fmt % args}")

    server = http.server.ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def new_session(username):
    key = secrets.token_hex(16)
    SESSIONS[key] = username
    return key


def session_account(key):
    return SESSIONS.get(key)


def ensure_dev_account(tokens=("12345678", "22222222")):
    """First run: a "dev" account owning the test launcher tokens, with a random password printed
    once, so a fresh install can log in. Returns the password, or None if accounts already exist."""
    data = load()
    if data["accounts"]:
        return None
    password = secrets.token_urlsafe(9)
    create(DEV_ACCOUNT, password, data)
    for t in tokens:
        data["launcher_tokens"][t] = DEV_ACCOUNT
    save(data)
    return password


def main(argv):
    if len(argv) >= 3 and argv[0] == "create":
        err = create(argv[1], argv[2])
    elif len(argv) >= 3 and argv[0] == "password":
        err = set_password(argv[1], argv[2])
    elif len(argv) >= 3 and argv[0] == "token":
        err = set_token(argv[1], argv[2])
    elif len(argv) >= 2 and argv[0] in ("suspend", "unsuspend"):
        err = set_suspended(argv[1], argv[0] == "suspend")
    elif argv[:1] == ["list"]:
        data = load()
        tokens = {}
        for t, u in data["launcher_tokens"].items():
            tokens.setdefault(u, []).append(t)
        for key, acc in sorted(data["accounts"].items()):
            print(f"{acc['name']}{' (suspended)' if acc.get('suspended') else ''}: launcher tokens {tokens.get(key, [])}")
        return 0
    else:
        print(__doc__)
        return 1
    print(err or "ok")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
