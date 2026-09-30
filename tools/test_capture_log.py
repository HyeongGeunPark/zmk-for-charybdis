#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for capture_log.py with a FAKE pyserial. No hardware and no pyserial install needed.

    py test_capture_log.py -v

What this proves: line prefixing and console echo, partial-line / UTF-8 / invalid-byte handling,
ANSI stripping, reconnect markers after SerialException (from both in_waiting and read), shared
MARK timestamps across several files, clean shutdown (footer, flushed partial, file handles closed),
a blocked console not stalling the readers, the data-quality counters, the missing-pyserial message.

What it can NOT prove: anything about the real pyserial/Windows driver/USB device (see README).
"""

import io
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "capture_log.py")
sys.path.insert(0, HERE)
import capture_log as cl  # noqa: E402

FAST = ["--retry-interval", "0.02", "--read-timeout", "0.02"]
TS = r"\d\d:\d\d:\d\d\.\d{3}"


# ------------------------------------------------------------------ fake pyserial

class FakeSerialException(OSError):
    """pyserial's SerialException derives from IOError (== OSError)."""


class Session:
    """What one open() of a fake port will deliver. push() bytes live or fail() to simulate unplug."""

    def __init__(self):
        self.q = queue.Queue()
        self.consumed = 0

    def push(self, data):
        self.q.put(data)
        return self

    def fail(self, exc, where="in_waiting"):
        self.q.put(("raise", exc, where))
        return self


class FakeSerial:
    def __init__(self, session, timeout):
        self.session = session
        self.timeout = timeout or 0.02
        self.is_open = True
        self.dtr = None
        self.rts = None
        self._buf = bytearray()
        self._exc = None  # (exception, where)

    def _pump(self):
        while self._exc is None:
            try:
                ev = self.session.q.get_nowait()
            except queue.Empty:
                return
            if isinstance(ev, (bytes, bytearray)):
                self._buf.extend(ev)
            else:
                self._exc = (ev[1], ev[2])

    def _check(self):
        if not self.is_open:
            raise FakeSerialException("Attempting to use a port that is not open")

    @property
    def in_waiting(self):
        self._check()
        self._pump()
        if self._buf:
            return len(self._buf)
        if self._exc and self._exc[1] == "in_waiting":
            raise self._exc[0]
        return 0

    def read(self, size=1):
        self._check()
        self._pump()
        if not self._buf:
            if self._exc and self._exc[1] == "read":
                raise self._exc[0]
            if self._exc:
                raise self._exc[0]
            time.sleep(min(self.timeout, 0.02))
            self._pump()
        out = bytes(self._buf[:size])
        del self._buf[:size]
        self.session.consumed += len(out)
        return out

    def close(self):
        self.is_open = False


class FakeSerialModule:
    SerialException = FakeSerialException
    VERSION = "fake-0"

    def __init__(self):
        self.ports = {}
        self.open_calls = []
        self._lock = threading.Lock()

    def queue_open(self, port, item):
        """item = Session (open succeeds) or an Exception instance (open fails)."""
        with self._lock:
            self.ports.setdefault(port.upper(), []).append(item)

    def Serial(self, port=None, baudrate=9600, timeout=None, **kw):  # noqa: N802 (pyserial API)
        with self._lock:
            self.open_calls.append(port)
            q = self.ports.get(str(port).upper())
            if not q:
                raise FakeSerialException(
                    "could not open port %r: FileNotFoundError(2, 'The system cannot find the file "
                    "specified.', None, 2)" % port)
            item = q.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeSerial(item, timeout)


class FakeListPorts:
    def __init__(self):
        self.infos = []

    def comports(self, include_links=False):
        return list(self.infos)


class FakeStdin:
    """Blocking readline() like a console; send(None) = EOF."""

    def __init__(self):
        self.q = queue.Queue()

    def send(self, text):
        self.q.put(text)

    def readline(self):
        item = self.q.get()
        return "" if item is None else item


class BlockingStdout:
    """stdout whose write() blocks until gate is set: a Windows console paused by QuickEdit selection."""

    def __init__(self):
        self.gate = threading.Event()
        self.chunks = []

    def write(self, text):
        self.gate.wait(15)
        self.chunks.append(text)
        return len(text)

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.chunks)


# ------------------------------------------------------------------ harness

ACTIVE_RUNS = []


def stop_all_runs():
    """Safety net: a failing assertion must never leave a capture running and hang the test process."""
    for r in ACTIVE_RUNS:
        r.stop.set()
    for r in ACTIVE_RUNS:
        r.thread.join(5.0)
    ACTIVE_RUNS.clear()


class Run:
    def __init__(self, argv, **kw):
        self.stop = threading.Event()
        self.result = []
        self.error = []
        ACTIVE_RUNS.append(self)

        def target():
            try:
                self.result.append(cl.main(argv, stop_event=self.stop, **kw))
            except BaseException as exc:  # surfaced by finish()
                self.error.append(exc)

        self.thread = threading.Thread(target=target, name="main-under-test", daemon=True)
        self.thread.start()

    def finish(self, timeout=8.0):
        self.stop.set()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise AssertionError("main() did not return within %.1fs after stop" % timeout)
        if self.error:
            raise self.error[0]
        return self.result[0]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="caplog_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake = FakeSerialModule()
        self.lp = FakeListPorts()
        saved = (cl.serial, cl.list_ports, sys.stdout)
        cl.serial, cl.list_ports = self.fake, self.lp
        self.stdout = sys.stdout = io.StringIO()

        def restore():
            cl.serial, cl.list_ports, sys.stdout = saved
        self.addCleanup(restore)
        self.addCleanup(stop_all_runs)  # registered last => runs first (before the fakes are unpatched)

    def argv(self, *extra):
        return list(extra) + ["--outdir", self.tmp] + FAST

    def log_path(self, name, timeout=5.0):
        pat = re.compile(r"^%s_\d{8}_\d{6}(_\d+)?\.log$" % re.escape(name))
        end = time.time() + timeout
        while time.time() < end:
            hits = [f for f in os.listdir(self.tmp) if pat.match(f)]
            if hits:
                return os.path.join(self.tmp, sorted(hits)[-1])
            time.sleep(0.01)
        self.fail("no log file for %r in %s: %s" % (name, self.tmp, os.listdir(self.tmp)))

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()

    def wait_for(self, predicate, what, path=None, timeout=8.0):
        end = time.time() + timeout
        while time.time() < end:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("timeout waiting for %s%s" % (what, ("\n--- file ---\n" + self.read(path)) if path else ""))

    def wait_text(self, path, needle, timeout=8.0):
        self.wait_for(lambda: needle in self.read(path), "%r in %s" % (needle, os.path.basename(path)),
                      path, timeout)


# ------------------------------------------------------------------ tests: pure pieces

class IdentityTests(unittest.TestCase):
    """Following a board to a new COM number must never jump to a sibling port."""

    def test_no_identity_without_location_suffix(self):
        rec = {"vid": 0x1D50, "pid": 0x615E, "serial": "71FB7A39AFC7297C", "location": None}
        self.assertIsNone(cl.identity_of(rec))  # pyserial reports no LOCATION on some Windows PCs
        self.assertIsNone(cl.identity_of(dict(rec, location="1-2")))

    def test_identity_tells_sibling_ports_apart_when_location_is_known(self):
        rec = {"vid": 0x1D50, "pid": 0x615E, "serial": "71FB7A39AFC7297C"}
        a = cl.identity_of(dict(rec, location="1-2:1.0"))
        b = cl.identity_of(dict(rec, location="1-2:1.2"))
        self.assertIsNotNone(a)
        self.assertNotEqual(a, b)


class LineAssemblerTests(unittest.TestCase):
    def test_first_byte_timestamp_and_split_lines(self):
        a = cl.LineAssembler()
        t1, t2, t3 = datetime(2026, 1, 1, 10, 0, 0), datetime(2026, 1, 1, 10, 0, 1), datetime(2026, 1, 1, 10, 0, 2)
        self.assertEqual(a.feed(b"abc", t1), [])
        self.assertTrue(a.pending)
        self.assertEqual(a.feed(b"def\r\nghi\nj", t2), [(t1, "abcdef"), (t2, "ghi")])
        self.assertEqual(a.feed(b"kl\n", t3), [(t2, "jkl")])
        self.assertFalse(a.pending)

    def test_utf8_split_across_chunks_and_invalid_bytes(self):
        a = cl.LineAssembler()
        t = datetime(2026, 1, 1)
        data = "한글\n".encode("utf-8")
        self.assertEqual(a.feed(data[:2], t), [])
        self.assertEqual(a.feed(data[2:], t), [(t, "한글")])
        out = a.feed(b"bad\xff\xfebytes\n", t)
        self.assertEqual(out, [(t, "bad\ufffd\ufffdbytes")])

    def test_ansi_and_control_chars(self):
        t = datetime(2026, 1, 1)
        raw = b"\x1b[1;31m[00:00:01.000,000] <err> x: boom\x1b[0m\x00\x07\n"
        self.assertEqual(cl.LineAssembler(strip_ansi=True).feed(raw, t),
                         [(t, "[00:00:01.000,000] <err> x: boom\\x00\\x07")])
        kept = cl.LineAssembler(strip_ansi=False).feed(raw, t)[0][1]
        self.assertIn("\x1b[1;31m", kept)

    def test_idle_flush_and_cap(self):
        a = cl.LineAssembler(max_line_bytes=10)
        t = datetime(2026, 1, 1, 0, 0, 0)
        a.feed(b"uart:~$ ", t)
        self.assertIsNone(a.idle_flush(t + timedelta(seconds=1), 2.0))
        item = a.idle_flush(t + timedelta(seconds=2.5), 2.0)
        self.assertEqual(item, (t, "uart:~$ " + cl.LineAssembler.PARTIAL_TAG))
        self.assertFalse(a.pending)
        out = a.feed(b"x" * 11, t)  # over the cap without a newline
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0][1].endswith(cl.LineAssembler.PARTIAL_TAG))


# ------------------------------------------------------------------ tests: full capture flows

class CaptureFlowTests(Base):
    def test_line_prefix_and_console_tee(self):
        s = Session().push(b"[00:00:01.000,000] <inf> zmk: hello\r\n[00:00:01.500,250] <wrn> bt: second\r\n")
        self.fake.queue_open("COM7", s)
        before = datetime.now().replace(microsecond=0) - timedelta(seconds=1)
        run = Run(self.argv("--port", "COM7", "--name", "dongle"))
        path = self.log_path("dongle")
        self.wait_text(path, "second")
        self.assertEqual(run.finish(), 0)
        text = self.read(path)
        lines = text.splitlines()
        self.assertIn("\n", text)
        self.assertNotIn("\r", text, "device CR must be stripped, file uses LF only")
        self.assertRegex(lines[0], r"^%s ### date \d{4}-\d\d-\d\d$" % TS)
        self.assertRegex(text, r"(?m)^%s ### capture start name=dongle port=COM7 baud=115200" % TS)
        self.assertRegex(text, r"(?m)^%s ### connected COM7$" % TS)
        self.assertRegex(text, r"(?m)^%s \[00:00:01\.000,000\] <inf> zmk: hello$" % TS)
        self.assertRegex(text, r"(?m)^%s \[00:00:01\.500,250\] <wrn> bt: second$" % TS)
        self.assertRegex(text, r"(?m)^%s ### capture end name=dongle connections=1 bytes=\d+$" % TS)
        # host stamps are real, recent and non-decreasing
        stamps = [datetime.strptime(l[:12], "%H:%M:%S.%f") for l in lines]
        self.assertEqual(stamps, sorted(stamps))
        now_s = datetime.now().hour * 3600 + datetime.now().minute * 60 + datetime.now().second
        first_s = stamps[0].hour * 3600 + stamps[0].minute * 60 + stamps[0].second
        self.assertLess(abs(now_s - first_s), 10)
        self.assertGreaterEqual(datetime.now(), before)
        # console tee carries the same text with a [name] prefix
        out = self.stdout.getvalue()
        self.assertRegex(out, r"(?m)^\[dongle\] %s \[00:00:01\.000,000\] <inf> zmk: hello$" % TS)
        # file name pattern
        self.assertRegex(os.path.basename(path), r"^dongle_\d{8}_\d{6}\.log$")

    def test_reconnect_markers_after_serial_exception(self):
        gone = "ClearCommError failed (PermissionError(13, 'The device does not recognize the command.', None, 22))"
        s1 = Session().push(b"[00:00:01.000,000] <inf> a: before1\n").fail(FakeSerialException(gone), "in_waiting")
        s2 = Session().push(b"[00:00:00.500,000] <inf> a: after1\n").fail(FakeSerialException(gone), "read")
        s3 = Session().push(b"[00:00:00.400,000] <inf> a: after2\n")
        for item in (s1,
                     FakeSerialException("could not open port 'COM7': FileNotFoundError(2, 'not found', None, 2)"),
                     FakeSerialException("could not open port 'COM7': PermissionError(13, 'Access is denied.', None, 5)"),
                     s2, s3):
            self.fake.queue_open("COM7", item)
        run = Run(self.argv("--port", "COM7", "--name", "dongle"))
        path = self.log_path("dongle")
        self.wait_text(path, "after2")
        self.assertTrue(run.thread.is_alive(), "capture must keep running after SerialException")
        self.assertEqual(run.finish(), 0)
        text = self.read(path)
        seq = []
        for l in text.splitlines():
            for key in ("### connected", "### disconnected", "### reconnected", "before1", "after1", "after2"):
                if key in l:
                    seq.append(key)
                    break
        self.assertEqual(seq, ["### connected", "before1", "### disconnected", "### reconnected", "after1",
                               "### disconnected", "### reconnected", "after2"], text)
        self.assertEqual(text.count("### disconnected"), 2, "failed reopen attempts must not spam markers")
        self.assertRegex(text, r"(?m)^%s ### disconnected COM7 \(FakeSerialException: ClearCommError failed" % TS)
        self.assertIn("connections=3", text)
        self.assertEqual(self.fake.ports["COM7"], [], "every scripted open (2 failing ones included) was consumed")
        self.assertEqual(len(self.fake.open_calls), 5, "1 initial open + 2 failing retries + 2 reconnects")

    def test_marks_are_written_to_every_file_with_the_same_host_time(self):
        sd, sr = Session(), Session()
        self.fake.queue_open("COM11", sd)
        self.fake.queue_open("COM12", sr)
        stdin = FakeStdin()
        run = Run(self.argv("--port", "COM11", "--name", "dongle", "--port", "COM12", "--name", "right",
                            "--grep-mark"), stdin=stdin)
        pd, pr = self.log_path("dongle"), self.log_path("right")
        self.assertNotEqual(pd, pr)
        for p in (pd, pr):
            self.wait_text(p, "### connected")
        sd.push(b"[00:00:10.000,000] <inf> dongle: d-line\n")
        sr.push(b"[00:00:10.000,000] <inf> right: r-line\n")
        self.wait_text(pd, "d-line")
        self.wait_text(pr, "r-line")
        stdin.send("\n")
        for p in (pd, pr):
            self.wait_text(p, "### MARK 1")
        sd.push(b"[00:00:11.000,000] <inf> dongle: after-mark\n")
        stdin.send("felt freeze here\n")
        for p in (pd, pr):
            self.wait_text(p, "### MARK 2 felt freeze here")
        stdin.send(None)  # EOF: reader thread ends, captures keep running
        self.wait_text(pd, "after-mark")
        self.assertTrue(run.thread.is_alive())
        run.finish()

        def marks(path):  # {mark text: host timestamp}
            return {text: ts for ts, text in re.findall(r"(?m)^(%s) (### MARK \d+.*)$" % TS, self.read(path))}
        md, mr = marks(pd), marks(pr)
        self.assertEqual(sorted(md), ["### MARK 1", "### MARK 2 felt freeze here"])
        self.assertEqual(md, mr, "identical host timestamp in both files for each MARK")
        d_lines = self.read(pd).splitlines()
        idx = {k: next(i for i, l in enumerate(d_lines) if k in l) for k in ("d-line", "### MARK 1", "after-mark")}
        self.assertLess(idx["d-line"], idx["### MARK 1"])
        self.assertLess(idx["### MARK 1"], idx["after-mark"])
        self.assertNotIn("d-line", self.read(pr), "each file only holds its own port's lines")
        self.assertIn("r-line", self.read(pr))
        self.assertIn("MARK 1 inserted", self.stdout.getvalue())

    def test_clean_shutdown_flushes_pending_partial_and_closes_files(self):
        sinks = []
        real_sink = cl.LogSink

        class RecordingSink(real_sink):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                sinks.append(self)
        cl.LogSink = RecordingSink
        self.addCleanup(setattr, cl, "LogSink", real_sink)
        payload = b"[00:00:05.000,000] <inf> z: complete\n[00:00:05.100,000] <inf> z: no-newline-yet"
        s = Session().push(payload)
        self.fake.queue_open("COM7", s)
        run = Run(self.argv("--port", "COM7", "--name", "dongle", "--partial-timeout", "0"))
        path = self.log_path("dongle")
        self.wait_for(lambda: s.consumed >= len(payload), "bytes consumed", path)
        self.assertEqual(run.finish(), 0)
        text = self.read(path)
        self.assertRegex(text, r"(?m)^%s \[00:00:05\.100,000\] <inf> z: no-newline-yet \[partial line\]$" % TS)
        last = re.match(r"^%s ### capture end name=dongle connections=1 bytes=(\d+)$" % TS,
                        text.rstrip("\n").splitlines()[-1])
        self.assertIsNotNone(last, "last line must be the capture-end footer")
        self.assertEqual(int(last.group(1)), len(payload))
        self.assertFalse([t for t in threading.enumerate() if t.name.startswith("capture-")],
                         "capture threads must have exited")
        self.assertEqual(len(sinks), 1)
        self.assertTrue(all(k._fh is None for k in sinks), "log file handle must be closed on shutdown")
        os.remove(path)  # also fails on Windows if a handle is still open
        self.assertIn("Log files:", self.stdout.getvalue())


class ConsoleAndStatsTests(Base):
    def test_blocked_console_does_not_stall_the_capture(self):
        blocked = BlockingStdout()
        sys.stdout = blocked  # Base.setUp restores the real one on cleanup
        s = Session()
        self.fake.queue_open("COM7", s)
        run = Run(self.argv("--port", "COM7", "--name", "dongle"))
        path = self.log_path("dongle")
        # the reader would sit in print() forever if the console echo ran in its thread
        self.wait_text(path, "### connected", timeout=5)
        for i in range(60):
            s.push(("[00:00:%02d.000,000] <inf> a: line%d\n" % (i, i)).encode())
        self.wait_text(path, "line59", timeout=5)
        self.assertEqual(blocked.getvalue(), "", "console really was blocked while the file kept filling")
        blocked.gate.set()
        self.assertEqual(run.finish(), 0)
        self.assertIn("line59", blocked.getvalue(), "queued echo is delivered once the console is released")

    def test_full_console_queue_skips_echo_only_and_says_so(self):
        console = cl.Console(queue_size=5)
        blocked = BlockingStdout()
        saved = sys.stdout
        sys.stdout = blocked
        try:
            for i in range(40):
                console.line("x", "row%d" % i)
            blocked.gate.set()
            console.note("", "end")
            console.close()
        finally:
            sys.stdout = saved
        text = blocked.getvalue()
        self.assertIn("row0", text)
        self.assertRegex(text, r"-- \d+ console line\(s\) were not echoed")
        self.assertIn("-- end", text)

    def test_data_quality_counters(self):
        payload = (b"*** Booting Zephyr OS build v4.1.0 ***\r\n"
                   b"[00:00:01.000,000] <inf> a: fine\r\n"
                   b"\x1b[1;33m[00:00:01.100,000] <wrn> a: coloured but fine\x1b[0m\r\n"
                   b"--- 12 messages dropped ---\r\n"
                   b"\x1b[1;31m--- 5 messages dropped ---\x1b[0m\r\n"
                   b"[00:00:02.000,000] <dbg> torn li\r\n"
                   b"[00:00:03.000,000] <inf> a: tail without newline")
        s = Session().push(payload)
        self.fake.queue_open("COM7", s)
        run = Run(self.argv("--port", "COM7", "--name", "dongle", "--partial-timeout", "0"))
        path = self.log_path("dongle")
        self.wait_for(lambda: s.consumed >= len(payload), "bytes consumed", path)
        self.assertEqual(run.finish(), 0)
        text = self.read(path)
        m = re.search(r"(?m)^%s ### stats lines=(\d+) nonlog=(\d+) partial=(\d+) drop_markers=(\d+) "
                      r"dropped_messages=(\d+)$" % TS, text)
        self.assertIsNotNone(m, text)
        # 7 device lines: banner (the only non-log line), fine, coloured, 2 drop markers, "torn"
        # (still looks like a log line, so it cannot be told apart), tail (flushed as partial).
        self.assertEqual(tuple(int(g) for g in m.groups()), (7, 1, 1, 2, 17))
        self.assertLess(text.index("### stats"), text.index("### capture end"))
        self.assertRegex(self.stdout.getvalue(), r"drop_markers=2 dropped_messages=17")


# ------------------------------------------------------------------ tests: real entry point in a subprocess

class SubprocessTests(unittest.TestCase):
    def test_missing_pyserial_message_and_exit_code(self):
        code = ("import sys, runpy; sys.modules['serial'] = None; sys.argv = ['capture_log.py', '--list'];"
                "runpy.run_path(%r, run_name='__main__')" % SCRIPT)
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("py -m pip install pyserial", p.stderr)
        self.assertIn("pyserial is not installed", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
