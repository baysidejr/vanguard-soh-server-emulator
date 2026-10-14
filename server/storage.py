"""The server's saved data: a SQLite database (vanguard.db) next to the data files.

Every saved document (guilds, mail, the market, accounts, ...) keeps its old file path as its name,
so callers still pass `HOUSING_FILE` and so on: the database is `vanguard.db` in that file's
folder and the row is keyed by the file name. Characters get their own table, one row each, so
saving one field of one character no longer rewrites every character.

On first use an existing JSON file is imported and renamed to `<name>.imported` (kept as a
backup). `python storage.py export [folder]` writes everything back out as JSON files (for backups
or hand edits) and `python storage.py import <file.json>` loads one file in again, replacing what
the database has for it. `python storage.py set <first name> <field> <JSON value>` changes one
field of one character, e.g. `python storage.py set Ranger access_level 255` makes Ranger a GM
(do it while the character is offline). Uses only the standard library.
"""
import contextlib
import json
import os
import sqlite3
import sys
import threading

DB_NAME = "vanguard.db"
CHARACTERS = "characters.json"

_LOCK = threading.RLock()
_READY = set()


def _db_path(path):
    return os.path.join(os.path.dirname(os.path.abspath(path)), DB_NAME)


@contextlib.contextmanager
def _db(path):
    """A connection to the database for path (opened per call, so nothing stays locked)."""
    db = _db_path(path)
    with _LOCK:
        fresh = db not in _READY or not os.path.exists(db)
        c = sqlite3.connect(db, isolation_level=None, timeout=30)
        try:
            if fresh:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("CREATE TABLE IF NOT EXISTS documents (name TEXT PRIMARY KEY, data TEXT NOT NULL)")
                c.execute("CREATE TABLE IF NOT EXISTS characters (seq INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,"
                          " data TEXT NOT NULL)")
                c.execute("CREATE TABLE IF NOT EXISTS imported (name TEXT PRIMARY KEY)")
                _READY.add(db)
            c.execute("PRAGMA synchronous=FULL")
            yield c
        finally:
            c.close()


def _transaction(c, fn):
    with _LOCK:
        c.execute("BEGIN IMMEDIATE")
        try:
            out = fn()
        except BaseException:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")
        return out


def _import_file(path, c):
    """Load path's JSON file into the database the first time its name is used."""
    name = os.path.basename(path)
    if c.execute("SELECT 1 FROM imported WHERE name = ?", (name,)).fetchone():
        return
    data = None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass

    def run():
        c.execute("INSERT OR IGNORE INTO imported (name) VALUES (?)", (name,))
        if data is not None:
            _store(c, name, data)
    _transaction(c, run)
    if data is not None:
        try:
            os.replace(path, path + ".imported")
        except OSError:
            pass


def _store(c, name, data):
    if name == CHARACTERS:
        c.execute("DELETE FROM characters")
        c.executemany("INSERT INTO characters (seq, name, data) VALUES (?, ?, ?)",
                      [(i, ch["first"], json.dumps(ch)) for i, ch in enumerate(data)])
    else:
        c.execute("INSERT INTO documents (name, data) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET data = excluded.data",
                  (name, json.dumps(data)))


def read_json(path, default=None):
    """The saved document for path, or default when there is none."""
    with _db(path) as c:
        _import_file(path, c)
        row = c.execute("SELECT data FROM documents WHERE name = ?", (os.path.basename(path),)).fetchone()
    return json.loads(row[0]) if row else default


def write_json(path, data, **_dump_args):
    with _db(path) as c:
        _import_file(path, c)
        _transaction(c, lambda: _store(c, os.path.basename(path), data))


def read_characters(path):
    """Every character record, in the order they were created."""
    with _db(path) as c:
        _import_file(path, c)
        return [json.loads(d) for (d,) in c.execute("SELECT data FROM characters ORDER BY seq")]


def write_characters(path, chars):
    with _db(path) as c:
        _import_file(path, c)
        _transaction(c, lambda: _store(c, CHARACTERS, chars))


def update_character(path, name, fields):
    """Set fields ({key: value}, or a function that changes the record) on the character whose
    first name is name. False if there is none."""
    with _db(path) as c:
        _import_file(path, c)

        def run():
            row = c.execute("SELECT data FROM characters WHERE name = ?", (name,)).fetchone()
            if row is None:
                return False
            ch = json.loads(row[0])
            fields(ch) if callable(fields) else ch.update(fields)
            c.execute("UPDATE characters SET data = ? WHERE name = ?", (json.dumps(ch), name))
            return True
        return _transaction(c, run)


def write_json_atomic(path, data, **dump_args):
    """Write data as JSON to path so a crash or power cut mid-write can't leave a
    truncated file: write a temporary file next to it, then rename it over the old one."""
    dump_args.setdefault("indent", 2)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, **dump_args)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def export(folder, out):
    """Write every document (and the characters) in folder's database as JSON files into out."""
    os.makedirs(out, exist_ok=True)
    with _db(os.path.join(folder, CHARACTERS)) as c:
        names = [n for (n,) in c.execute("SELECT name FROM documents")]
    written = []
    for n in names:
        write_json_atomic(os.path.join(out, n), read_json(os.path.join(folder, n)))
        written.append(n)
    write_json_atomic(os.path.join(out, CHARACTERS), read_characters(os.path.join(folder, CHARACTERS)))
    return written + [CHARACTERS]


def import_file(src, folder):
    """Replace what folder's database has for src's file name with src's contents."""
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    target = os.path.join(folder, os.path.basename(src))
    with _db(target) as c:
        _transaction(c, lambda: (c.execute("INSERT OR IGNORE INTO imported (name) VALUES (?)",
                                           (os.path.basename(src),)),
                                 _store(c, os.path.basename(src), data)))


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    if argv[:1] == ["export"]:
        out = argv[1] if len(argv) > 1 else os.path.join(here, "export")
        for n in export(here, out):
            print(f"wrote {os.path.join(out, n)}")
    elif len(argv) == 2 and argv[0] == "import":
        import_file(argv[1], here)
        print(f"imported {argv[1]}")
    elif len(argv) == 4 and argv[0] == "set":
        try:
            value = json.loads(argv[3])
        except ValueError:
            value = argv[3]
        if not update_character(os.path.join(here, CHARACTERS), argv[1], {argv[2]: value}):
            print(f"No character named {argv[1]}.")
            return 1
        print(f"{argv[1]}: {argv[2]} = {value!r}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
