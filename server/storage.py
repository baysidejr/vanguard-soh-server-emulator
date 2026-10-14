"""Saving the server's JSON files safely."""
import json
import os


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
