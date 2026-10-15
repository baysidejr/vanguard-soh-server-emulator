"""Run every automated check and print one summary.

    python tools/check_all.py            # unit tests, content, scenarios, load test, fuzzing
    python tools/check_all.py --client   # also the smoke test with the real game client

Starts and stops its own servers (no server may be running on the default ports). The scenarios
and the load test use the normal database and remove their bot characters afterwards; the fuzzer
runs against a scratch copy of the data (a temporary --data-dir). Uses the standard library only.
"""
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server")
PY = sys.executable


def run(cmd, cwd=ROOT, timeout=900):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


def start_server(*extra):
    log = open(os.path.join(SERVER, "check_log.txt"), "w", encoding="utf-8")
    p = subprocess.Popen([PY, "-u", "login_stub.py", "--quiet-packets", *extra], cwd=SERVER,
                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    time.sleep(3)
    return p


def stop_server(p):
    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()


def server_errors():
    text = open(os.path.join(SERVER, "check_log.txt"), encoding="utf-8", errors="replace").read()
    return len(re.findall(r"Traceback|handler error|!!! error", text))


def port_free(port=10101):
    """False if a server already holds the login port: the checks would then talk to it instead
    of their own server."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    results = []
    if not port_free():
        print("FAIL  a server is already running on port 10101; stop it first (the checks start their own)")
        sys.exit(1)

    def note(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)

    code, out = run([PY, "-m", "unittest", "discover", "-p", "test_*.py"], cwd=SERVER)
    ran = re.search(r"Ran (\d+) tests", out)
    note("unit tests", code == 0, ran.group(0) if ran else out[-200:])
    code, out = run([PY, "content.py"], cwd=SERVER)
    note("content", out.strip().endswith("content OK"), out.strip().splitlines()[-1] if out.strip() else "")

    srv = start_server()
    try:
        run([PY, "tools/scenarios.py", "--setup"])
        code, out = run([PY, "tools/scenarios.py"], timeout=300)
        fails = re.search(r"(\d+) failed", out)
        note("scenarios", code == 0, fails.group(0) if fails else out[-300:])
        run([PY, "tools/loadtest.py", "--setup", "20"])
        code, out = run([PY, "tools/loadtest.py", "--bots", "20", "--seconds", "20"], timeout=300)
        steady = re.search(r"steady state[^\n]*", out)
        note("load test (20 bots)", code == 0 and "20/20" in out, steady.group(0) if steady else out[-300:])
    finally:
        run([PY, "tools/loadtest.py", "--cleanup"])
        stop_server(srv)
    errors = server_errors()
    note("server log (scenarios, load)", errors == 0, f"{errors} errors")

    with tempfile.TemporaryDirectory() as data:
        run([PY, "tools/loadtest.py", "--data-dir", data, "--setup", "1"])
        srv = start_server("--dev-commands", "--data-dir", data)
        try:
            code, out = run([PY, "tools/fuzz.py", "--data-dir", data, "--max-event", "0x900", "--per-event", "4",
                             "--raw", "10", "--log", os.path.join(SERVER, "check_log.txt")], timeout=900)
            summary = re.search(r"Handler errors in[^\n]*", out)
            note("fuzzing", code == 0 and summary is not None and summary.group(0).startswith("Handler errors in 0"),
                 summary.group(0) if summary else out[-300:])
        finally:
            stop_server(srv)
            time.sleep(1)

    if "--client" in sys.argv:
        code, out = run([PY, "tools/smoke_test.py"], timeout=900)
        note("smoke test (game client)", "PASS" in out, out.strip().splitlines()[-1] if out.strip() else "")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
