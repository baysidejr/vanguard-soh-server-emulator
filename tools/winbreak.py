"""A minimal breakpoint logger for the running 32-bit game client (Windows only).

Attaches to VGClient.exe as a debugger, puts an int3 on each given address, and logs every hit
(address, thread, registers, the first stack words) until the time is up; then it removes the
breakpoints and detaches, leaving the client running. Use it to see whether (and with what) a
client function runs while you play, e.g. which branch of Jump runs on a mounted double jump.

    python tools/winbreak.py --pid 1234 --seconds 30 0xbaf7e0 0x6eb1b0
    python tools/winbreak.py --seconds 30 0xbaf7e0          # the first VGClient.exe found

Each hit prints one line; --max-hits limits how many per address are printed (all are counted).
Only for debugging your own client. Uses ctypes and the standard library only.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

DEBUG_EVENT_EXCEPTION = 1
DEBUG_EVENT_EXIT_PROCESS = 5
DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
STATUS_BREAKPOINT = 0x80000003
STATUS_SINGLE_STEP = 0x80000004
STATUS_WX86_BREAKPOINT = 0x4000001F
STATUS_WX86_SINGLE_STEP = 0x4000001E
WOW64_CONTEXT_FULL = 0x10000 | 0x1 | 0x2 | 0x4    # control, integer, segments
PROCESS_ALL_ACCESS = 0x1F0FFF
THREAD_ALL_ACCESS = 0x1F03FF


class WOW64_FLOATING_SAVE_AREA(ctypes.Structure):
    _fields_ = [("ControlWord", wt.DWORD), ("StatusWord", wt.DWORD), ("TagWord", wt.DWORD),
                ("ErrorOffset", wt.DWORD), ("ErrorSelector", wt.DWORD), ("DataOffset", wt.DWORD),
                ("DataSelector", wt.DWORD), ("RegisterArea", ctypes.c_byte * 80), ("Cr0NpxState", wt.DWORD)]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [("ContextFlags", wt.DWORD), ("Dr0", wt.DWORD), ("Dr1", wt.DWORD), ("Dr2", wt.DWORD),
                ("Dr3", wt.DWORD), ("Dr6", wt.DWORD), ("Dr7", wt.DWORD), ("FloatSave", WOW64_FLOATING_SAVE_AREA),
                ("SegGs", wt.DWORD), ("SegFs", wt.DWORD), ("SegEs", wt.DWORD), ("SegDs", wt.DWORD),
                ("Edi", wt.DWORD), ("Esi", wt.DWORD), ("Ebx", wt.DWORD), ("Edx", wt.DWORD), ("Ecx", wt.DWORD),
                ("Eax", wt.DWORD), ("Ebp", wt.DWORD), ("Eip", wt.DWORD), ("SegCs", wt.DWORD),
                ("EFlags", wt.DWORD), ("Esp", wt.DWORD), ("SegSs", wt.DWORD),
                ("ExtendedRegisters", ctypes.c_byte * 512)]


class EXCEPTION_RECORD(ctypes.Structure):
    pass


EXCEPTION_RECORD._fields_ = [("ExceptionCode", wt.DWORD), ("ExceptionFlags", wt.DWORD),
                             ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
                             ("ExceptionAddress", ctypes.c_void_p), ("NumberParameters", wt.DWORD),
                             ("ExceptionInformation", ctypes.c_size_t * 15)]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", wt.DWORD)]


class DEBUG_EVENT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("Exception", EXCEPTION_DEBUG_INFO), ("raw", ctypes.c_byte * 160)]
    _fields_ = [("dwDebugEventCode", wt.DWORD), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
                ("u", _U)]


def find_pid(name="VGClient.exe"):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


class Debugger:
    def __init__(self, pid):
        self.pid = pid
        self.proc = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not self.proc:
            raise OSError(f"OpenProcess failed: {ctypes.get_last_error()}")
        self.original = {}          # address -> original byte
        self.rearm = {}             # thread id -> address to put the int3 back on after one step
        self.hits = {}

    def read(self, addr, n):
        buf = (ctypes.c_char * n)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.proc, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return b""
        return bytes(buf[:got.value])

    def write(self, addr, data):
        old = wt.DWORD()
        k32.VirtualProtectEx(self.proc, ctypes.c_void_p(addr), len(data), 0x40, ctypes.byref(old))
        done = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(self.proc, ctypes.c_void_p(addr), data, len(data), ctypes.byref(done))
        k32.VirtualProtectEx(self.proc, ctypes.c_void_p(addr), len(data), old.value, ctypes.byref(old))
        k32.FlushInstructionCache(self.proc, ctypes.c_void_p(addr), len(data))
        return ok

    def arm(self, addr):
        if addr not in self.original:
            self.original[addr] = self.read(addr, 1)
        self.write(addr, b"\xcc")

    def disarm_all(self):
        for addr, byte in self.original.items():
            if byte:
                self.write(addr, byte)

    def context(self, tid):
        th = k32.OpenThread(THREAD_ALL_ACCESS, False, tid)
        ctx = WOW64_CONTEXT()
        ctx.ContextFlags = WOW64_CONTEXT_FULL
        k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
        return th, ctx

    def run(self, seconds, max_hits):
        if not k32.DebugActiveProcess(self.pid):
            raise OSError(f"DebugActiveProcess failed: {ctypes.get_last_error()}")
        k32.DebugSetProcessKillOnExit(False)
        armed = False
        end = time.time() + seconds
        ev = DEBUG_EVENT()
        try:
            while time.time() < end:
                if not k32.WaitForDebugEvent(ctypes.byref(ev), 100):
                    if not armed:
                        continue
                    continue
                status = DBG_CONTINUE
                if ev.dwDebugEventCode == DEBUG_EVENT_EXIT_PROCESS:
                    print("the client exited")
                    return
                if ev.dwDebugEventCode == DEBUG_EVENT_EXCEPTION:
                    rec = ev.u.Exception.ExceptionRecord
                    code = rec.ExceptionCode
                    if code in (STATUS_BREAKPOINT, STATUS_WX86_BREAKPOINT):
                        th, ctx = self.context(ev.dwThreadId)
                        addr = ctx.Eip - 1
                        if addr in self.original:
                            n = self.hits[addr] = self.hits.get(addr, 0) + 1
                            if n <= max_hits:
                                stack = self.read(ctx.Esp, 16)
                                words = [int.from_bytes(stack[i:i + 4], "little") for i in range(0, len(stack), 4)]
                                print(f"{time.strftime('%H:%M:%S')} hit {addr:#x} #{n} tid {ev.dwThreadId} "
                                      f"eax={ctx.Eax:#x} ecx={ctx.Ecx:#x} edx={ctx.Edx:#x} ebx={ctx.Ebx:#x} "
                                      f"esi={ctx.Esi:#x} edi={ctx.Edi:#x} [esp]=" + " ".join(f"{w:#x}" for w in words),
                                      flush=True)
                            self.write(addr, self.original[addr])
                            ctx.Eip = addr
                            ctx.EFlags |= 0x100                  # one step, then put the int3 back
                            k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
                            self.rearm[ev.dwThreadId] = addr
                        elif not armed:
                            for a in list(self.original):
                                self.arm(a)
                            armed = True
                            print(f"attached; breakpoints on {', '.join(hex(a) for a in self.original)}", flush=True)
                        k32.CloseHandle(th)
                    elif code in (STATUS_SINGLE_STEP, STATUS_WX86_SINGLE_STEP) and ev.dwThreadId in self.rearm:
                        self.arm(self.rearm.pop(ev.dwThreadId))
                    else:
                        status = DBG_EXCEPTION_NOT_HANDLED
                k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
        finally:
            self.disarm_all()
            k32.DebugActiveProcessStop(self.pid)
        print("hits: " + (", ".join(f"{a:#x} x{n}" for a, n in sorted(self.hits.items())) or "none"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("addresses", nargs="+", type=lambda v: int(v, 0))
    ap.add_argument("--pid", type=int)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--max-hits", type=int, default=20)
    a = ap.parse_args()
    pid = a.pid or find_pid()
    if not pid:
        sys.exit("VGClient.exe is not running")
    d = Debugger(pid)
    for addr in a.addresses:
        d.original[addr] = d.read(addr, 1)
    d.run(a.seconds, a.max_hits)


if __name__ == "__main__":
    main()
