#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""capture_log.py - save ZMK / Zephyr USB-CDC-ACM logs to timestamped files.

Written for Windows 11 + Python 3.14 + pyserial, works elsewhere too.

    py capture_log.py --list
    py capture_log.py --port COM5 --name dongle --mark
    py capture_log.py --port COM5 --name dongle --port COM7 --name right --mark

Every log line is written as

    HH:MM:SS.mmm [00:00:12.345,678] <inf> module: message
    ^ host clock  ^ device uptime as printed by Zephyr

Lines starting with "###" are written by this tool, not by the firmware:
"### connected", "### disconnected", "### reconnected", "### MARK <n>", ...

See README.md next to this file.
"""

import argparse
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime

__version__ = "1.1"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_PYSERIAL = 3
EXIT_OUTPUT = 4

PYSERIAL_INSTALL_CMD = "py -m pip install pyserial"

# ZMK app/Kconfig @ 9ebbeff0: USB_DEVICE_VID default 0x1D50, USB_DEVICE_PID default 0x615E.
ZMK_VID_PID = (0x1D50, 0x615E)
# Zephyr subsys/usb/device/Kconfig: USB_DEVICE_VID default 0x2FE3 (used if a board does not override it).
ZEPHYR_DEFAULT_VID = 0x2FE3
# Case-insensitive hints looked for in description / manufacturer / product. On Windows pyserial only
# reports the driver's friendly name ("USB Serial Device (COM5)") and manufacturer "Microsoft", so these
# mostly help on Linux/macOS; VID:PID is the reliable key on Windows.
NAME_HINTS = ("zmk", "zephyr", "seeed", "nrf52", "nice!nano", "nicenano", "charybdis", "xi-mk1")

# pyserial modules. Loaded lazily by load_pyserial(); tests replace these with fakes.
serial = None
list_ports = None


class SelectionError(Exception):
    """Port selection failed; the message is shown to the user."""


# --------------------------------------------------------------------------- pyserial loading

def load_pyserial():
    """Import pyserial or exit with a clear message and the install command."""
    global serial, list_ports
    if serial is not None and list_ports is not None:
        return
    try:
        import serial as _serial
    except ImportError:
        sys.stderr.write(
            "ERROR: pyserial is not installed for this Python:\n"
            "    %s  (%s)\n\n"
            "Install it with:\n\n"
            "    %s\n\n"
            "(If the 'py' launcher is missing, use:  \"%s\" -m pip install pyserial)\n"
            % (sys.executable, sys.version.split()[0], PYSERIAL_INSTALL_CMD, sys.executable))
        raise SystemExit(EXIT_NO_PYSERIAL)
    if not hasattr(_serial, "Serial"):
        sys.stderr.write(
            "ERROR: a module named 'serial' is installed but it is not pyserial "
            "(it has no Serial class).\n"
            "The unrelated PyPI package 'serial' shadows it. Fix with:\n\n"
            "    py -m pip uninstall serial\n"
            "    %s\n" % PYSERIAL_INSTALL_CMD)
        raise SystemExit(EXIT_NO_PYSERIAL)
    try:
        import serial.tools.list_ports as _lp
    except ImportError as exc:
        sys.stderr.write(
            "ERROR: pyserial looks broken (%s).\nReinstall with:\n\n"
            "    py -m pip install --force-reinstall pyserial\n" % exc)
        raise SystemExit(EXIT_NO_PYSERIAL)
    serial, list_ports = _serial, _lp


# --------------------------------------------------------------------------- small helpers

def fmt_ts(dt):
    """Host wall-clock stamp 'HH:MM:SS.mmm'."""
    return "%s.%03d" % (dt.strftime("%H:%M:%S"), dt.microsecond // 1000)


def describe_exc(exc):
    return " ".join(("%s: %s" % (type(exc).__name__, exc)).split())[:300]


def open_failure_hint(exc):
    s = str(exc).lower()
    if "access is denied" in s or "permissionerror" in s or "errno 13" in s or "busy" in s:
        return ("port is busy (another program such as PuTTY / Arduino Serial Monitor / "
                "another capture holds it) or the board is just re-enumerating")
    if "cannot find the file" in s or "filenotfounderror" in s or "no such file" in s or "errno 2" in s:
        return "port not present (board unplugged, resetting, asleep or in bootloader)"
    return ""


def sanitize_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned or "port"


def normalize_port(text):
    """'com5' -> 'COM5'. Anything else (e.g. /dev/ttyACM0) is returned unchanged."""
    text = text.strip()
    if re.fullmatch(r"(?i)com\d+", text):
        return text.upper()
    return text


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_CTRL_KEEP_ESC_RE = re.compile(r"[\x00-\x08\x0b-\x1a\x1c-\x1f\x7f]")

# Zephyr log_output.c: "[hh:mm:ss.mmm,uuu] <lvl> module: msg" and "--- N messages dropped ---".
# Used only for the data-quality counters; a line is never rejected or altered because of them.
_LOG_LINE_RE = re.compile(r"^\[\d\d:\d\d:\d\d\.\d{3},\d{3}\] <[a-z]{3}> ")
_DROPPED_RE = re.compile(r"^--- (\d+) messages dropped ---")


# --------------------------------------------------------------------------- port records

def port_record(p):
    """Flatten a pyserial ListPortInfo into a dict (missing fields become None)."""
    def g(attr):
        val = getattr(p, attr, None)
        return val if val not in ("", "n/a") else None
    return {
        "device": getattr(p, "device", None) or str(p),
        "vid": g("vid"), "pid": g("pid"),
        "serial": g("serial_number"), "location": g("location"),
        "manufacturer": g("manufacturer"), "product": g("product"),
        "interface": g("interface"),
        "description": getattr(p, "description", None), "hwid": getattr(p, "hwid", None),
    }


def list_records():
    try:
        recs = [port_record(p) for p in list_ports.comports()]
    except Exception as exc:  # enumeration must never kill the tool
        sys.stderr.write("WARNING: could not enumerate serial ports: %s\n" % describe_exc(exc))
        return []

    def key(r):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", r["device"] or "")]
    return sorted(recs, key=key)


def is_candidate(rec):
    vid, pid = rec.get("vid"), rec.get("pid")
    if (vid, pid) == ZMK_VID_PID or vid == ZEPHYR_DEFAULT_VID:
        return True
    text = " ".join(str(rec.get(k) or "") for k in ("description", "manufacturer", "product")).lower()
    return any(h in text for h in NAME_HINTS)


def identity_of(rec):
    """Stable identity of a USB CDC function, independent of the COM number.

    (vid, pid, serial, interface suffix of the location string). The suffix (Windows 'x.2',
    Linux '1.2') tells apart the two CDC ports of a dongle that has both Studio and logging.
    Returns None when the serial number is unknown."""
    if not rec.get("serial") or rec.get("vid") is None or rec.get("pid") is None:
        return None
    loc = rec.get("location") or ""
    suffix = loc.split(":", 1)[1] if ":" in loc else None
    if suffix is None:
        # pyserial often reports no LOCATION on Windows. Without it two CDC ports of the same
        # board (same VID/PID/serial) are indistinguishable, so following a COM number change
        # could silently jump to the wrong port. Refuse to follow; the user restarts the tool.
        return None
    return (rec["vid"], rec["pid"], str(rec["serial"]).upper(), suffix)


def render_port_table(records):
    headers = ["  PORT", "VID:PID", "SERIAL", "LOCATION", "MANUFACTURER", "PRODUCT", "DESCRIPTION"]
    rows = []
    for r in records:
        vidpid = ("%04X:%04X" % (r["vid"], r["pid"])) if r["vid"] is not None and r["pid"] is not None else "-"
        rows.append([
            ("* " if is_candidate(r) else "  ") + str(r["device"]),
            vidpid, r["serial"] or "-", r["location"] or "-", r["manufacturer"] or "-",
            r["product"] or "-", r["description"] or "-"])
    widths = [max(len(headers[c]), *(len(row[c]) for row in rows)) if rows else len(headers[c])
              for c in range(len(headers))]
    lines = ["  ".join(h.ljust(widths[c]) for c, h in enumerate(headers)).rstrip()]
    for row in rows:
        lines.append("  ".join(v.ljust(widths[c]) for c, v in enumerate(row)).rstrip())
    lines.append("")
    lines.append("* = looks like a ZMK/Zephyr USB device (VID:PID 1D50:615E = ZMK default, "
                 "or VID 2FE3 = Zephyr default, or a name hint).")
    lines.append("On Windows pyserial reports the manufacturer of the DRIVER (usually 'Microsoft') and no "
                 "product string;")
    lines.append("tell boards apart by VID:PID, SERIAL (unique per nRF52840 chip) and LOCATION (':x.N' = USB "
                 "interface number; often empty on Windows).")
    return "\n".join(lines)


# --------------------------------------------------------------------------- output plumbing

class Console:
    """Console output that can never block a serial reader; never raises.

    Writing to a Windows console can stall for seconds or for good (QuickEdit text selection, a
    slow terminal window). A reader thread stuck in print() stops draining its COM port, the
    board's CDC ring fills up and log lines are torn. So everything goes through a bounded queue
    that a single writer thread drains. If the queue is full, device lines are left out of the
    echo only (the log files are written before the echo and never depend on it) and the number
    of skipped lines is reported once the console catches up."""

    QUEUE_SIZE = 4000

    def __init__(self, show_lines=True, queue_size=QUEUE_SIZE):
        self.show_lines = show_lines
        self._q = queue.Queue(maxsize=queue_size)
        self._lock = threading.Lock()
        self._skipped = 0
        self._writer = threading.Thread(target=self._pump, name="console", daemon=True)
        self._writer.start()

    @staticmethod
    def _print(text):
        try:
            print(text, file=sys.stdout, flush=True)
        except Exception:
            pass

    def _pump(self):
        while True:
            text = self._q.get()
            if text is None:
                return
            self._print(text)
            if self._q.empty():
                with self._lock:
                    skipped, self._skipped = self._skipped, 0
                if skipped:
                    self._print("-- %d console line(s) were not echoed because the console was too slow; "
                                "the log files are complete" % skipped)

    def _emit(self, text, droppable):
        try:
            if droppable:
                self._q.put_nowait(text)
            else:
                self._q.put(text, timeout=1.0)
        except queue.Full:
            with self._lock:
                self._skipped += 1

    def line(self, label, text):
        if self.show_lines:
            self._emit("[%s] %s" % (label, text), droppable=True)

    def note(self, label, text):
        self._emit("[%s] -- %s" % (label, text) if label else "-- %s" % text, droppable=False)

    def close(self, timeout=3.0):
        """Print what is still queued (bounded wait) and stop the writer thread."""
        try:
            self._q.put(None, timeout=timeout)
        except queue.Full:
            return
        self._writer.join(timeout)


class LogSink:
    """One log file. Every write is flushed; safe to call from several threads."""

    def __init__(self, outdir, name, start_dt):
        os.makedirs(outdir, exist_ok=True)
        base = "%s_%s" % (name, start_dt.strftime("%Y%m%d_%H%M%S"))
        suffix = 0
        while True:
            path = os.path.join(outdir, "%s%s.log" % (base, "" if suffix == 0 else "_%d" % suffix))
            try:
                self._fh = open(path, "x", encoding="utf-8", newline="\n")
                break
            except FileExistsError:
                suffix += 1
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._date = None
        self.lines = 0

    def write(self, ts, text):
        text = _CTRL_RE.sub(lambda m: "\\x%02x" % ord(m.group()), text.replace("\r", "\\r").replace("\n", " "))
        with self._lock:
            if self._fh is None:
                return
            out = ""
            if ts.date() != self._date:
                self._date = ts.date()
                out += "%s ### date %s\n" % (fmt_ts(ts), ts.strftime("%Y-%m-%d"))
                self.lines += 1
            out += "%s %s\n" % (fmt_ts(ts), text)
            self.lines += 1
            self._fh.write(out)
            self._fh.flush()

    def close(self):
        with self._lock:
            if self._fh is None:
                return
            try:
                self._fh.flush()
                os.fsync(self._fh.fileno())
            except OSError:
                pass
            self._fh.close()
            self._fh = None


# --------------------------------------------------------------------------- line assembly

class LineAssembler:
    """Turns arbitrary byte chunks into (host_time_of_first_byte, text) lines.

    Bytes are buffered until '\\n' and only then decoded, so a UTF-8 character split across two
    reads is decoded correctly and undecodable bytes become U+FFFD instead of raising."""

    PARTIAL_TAG = " [partial line]"

    def __init__(self, strip_ansi=True, max_line_bytes=65536):
        self.strip_ansi = strip_ansi
        self.max_line_bytes = max_line_bytes
        self._buf = bytearray()
        self._start = None
        self._last = None

    def _decode(self, raw):
        text = raw.decode("utf-8", errors="replace")
        text = text.rstrip("\r")
        if self.strip_ansi:
            text = _ANSI_RE.sub("", text).replace("\x1b", "")
            text = _CTRL_RE.sub(lambda m: "\\x%02x" % ord(m.group()), text)
        else:
            text = _CTRL_KEEP_ESC_RE.sub(lambda m: "\\x%02x" % ord(m.group()), text)
        return text

    @property
    def pending(self):
        return bool(self._buf)

    def feed(self, data, now):
        out = []
        if not data:
            return out
        if not self._buf:
            self._start = now
        self._last = now
        self._buf.extend(data)
        while True:
            i = self._buf.find(b"\n")
            if i < 0:
                break
            raw = bytes(self._buf[:i])
            del self._buf[:i + 1]
            out.append((self._start, self._decode(raw)))
            self._start = now  # whatever follows arrived in this very chunk
        if not self._buf:
            self._start = None
        elif len(self._buf) > self.max_line_bytes:
            out.append((self._start, self._decode(bytes(self._buf)) + self.PARTIAL_TAG))
            self._buf.clear()
            self._start = None
        return out

    def idle_flush(self, now, timeout):
        """Emit a pending partial line that has seen no new bytes for `timeout` seconds."""
        if self._buf and timeout > 0 and (now - self._last).total_seconds() >= timeout:
            return self.flush()
        return None

    def flush(self):
        if not self._buf:
            return None
        item = (self._start, self._decode(bytes(self._buf)) + self.PARTIAL_TAG)
        self._buf.clear()
        self._start = None
        return item


# --------------------------------------------------------------------------- one port = one thread

class Capture(threading.Thread):
    """Reads one serial port forever, surviving unplug / reset / re-enumeration."""

    NO_DATA_HINT_S = 15.0

    def __init__(self, name, port, sink, console, stop, *, baud=115200, strip_ansi=True,
                 partial_timeout=2.0, retry_interval=0.25, read_timeout=0.1, follow=True,
                 identity=None, port_info=None):
        super().__init__(name="capture-%s" % name, daemon=True)
        self.label = name
        self.port = port
        self.sink = sink
        self.console = console
        self.stop = stop
        self.baud = baud
        self.assembler = LineAssembler(strip_ansi=strip_ansi)
        self.partial_timeout = partial_timeout
        self.retry_interval = retry_interval
        self.read_timeout = read_timeout
        self.follow = follow
        self.identity = identity
        self.port_info = port_info
        self.state = "starting"        # starting | waiting | connected | disconnected
        self.connections = 0
        self.bytes_total = 0
        # Data-quality counters over device lines (not the tool's own '###' lines).
        self.dev_lines = 0
        self.nonlog_lines = 0      # do not look like "[hh:mm:ss.mmm,uuu] <lvl> ..." (boot banner, torn lines)
        self.partial_lines = 0     # flushed without a newline (idle timeout, disconnect, shutdown)
        self.drop_markers = 0      # "--- N messages dropped ---" printed by the firmware
        self.dropped_messages = 0  # sum of those N
        self._fail_streak = 0
        self._last_scan = float("-inf")
        self._last_note = (None, 0.0)

    # ---- output -------------------------------------------------------------------------------
    def emit_line(self, ts, text):
        """A line that came from the device (as opposed to marker(), the tool's own lines)."""
        self.dev_lines += 1
        m = _DROPPED_RE.match(text)
        if m:
            self.drop_markers += 1
            self.dropped_messages += int(m.group(1))
        elif text.endswith(LineAssembler.PARTIAL_TAG):
            self.partial_lines += 1
        elif not _LOG_LINE_RE.match(text):
            self.nonlog_lines += 1
        self.sink.write(ts, text)
        self.console.line(self.label, "%s %s" % (fmt_ts(ts), text))

    def stats_text(self):
        return ("lines=%d nonlog=%d partial=%d drop_markers=%d dropped_messages=%d"
                % (self.dev_lines, self.nonlog_lines, self.partial_lines, self.drop_markers,
                   self.dropped_messages))

    def marker(self, text, ts=None):
        ts = ts or datetime.now()
        self.sink.write(ts, text)
        self.console.line(self.label, "%s %s" % (fmt_ts(ts), text))

    def _rate_limited_note(self, text, every=10.0):
        last_text, last_time = self._last_note
        now = time.monotonic()
        if text != last_text or now - last_time >= every:
            self._last_note = (text, now)
            self.console.note(self.label, text)

    # ---- port (re)discovery ---------------------------------------------------------------------
    def _resolve_port(self):
        """If the COM number changed after re-enumeration, follow the same USB function."""
        if not (self.follow and self.identity) or self._fail_streak < 4:
            return self.port
        if time.monotonic() - self._last_scan < 2.0:
            return self.port
        self._last_scan = time.monotonic()
        try:
            recs = [port_record(p) for p in list_ports.comports()]
        except Exception:
            return self.port
        if any((r["device"] or "").upper() == self.port.upper() for r in recs):
            return self.port
        matches = [r["device"] for r in recs if identity_of(r) == self.identity]
        if len(matches) == 1:
            old, self.port = self.port, matches[0]
            self.marker("### port changed %s -> %s (same USB serial/interface)" % (old, self.port))
        return self.port

    def _open(self, port):
        ser = serial.Serial(port, self.baud, timeout=self.read_timeout)
        try:  # pyserial already asserts DTR/RTS on open; be explicit, ignore driver quirks
            ser.dtr = True
            ser.rts = True
        except Exception:
            pass
        return ser

    # ---- main loop -----------------------------------------------------------------------------
    def run(self):
        started = datetime.now()
        self.marker("### capture start name=%s port=%s baud=%d tool=capture_log.py/%s"
                    % (self.label, self.port, self.baud, __version__), started)
        if self.port_info:
            r = self.port_info
            self.marker("### port info vid:pid=%s serial=%s location=%s manufacturer=%s description=%s" % (
                ("%04X:%04X" % (r["vid"], r["pid"])) if r.get("vid") is not None else "-",
                r.get("serial") or "-", r.get("location") or "-", r.get("manufacturer") or "-",
                r.get("description") or "-"))
        try:
            while not self.stop.is_set():
                try:
                    self._one_connection_cycle()
                except Exception as exc:  # unexpected: log once, keep the thread alive
                    self._fail_streak += 1
                    text = "### capture error (continuing): %s" % describe_exc(exc)
                    if text != self._last_note[0]:
                        self.marker(text)
                    self._last_note = (text, time.monotonic())
                    self.stop.wait(max(self.retry_interval, 0.5))
        finally:
            item = self.assembler.flush()
            if item:
                self.emit_line(*item)
            self.marker("### stats " + self.stats_text())
            self.marker("### capture end name=%s connections=%d bytes=%d"
                        % (self.label, self.connections, self.bytes_total))
            self.sink.close()

    def _one_connection_cycle(self):
        port = self._resolve_port()
        try:
            ser = self._open(port)
        except (serial.SerialException, OSError, ValueError) as exc:
            self._fail_streak += 1
            if self.state == "starting":
                self.state = "waiting"
            hint = open_failure_hint(exc)
            self._rate_limited_note("cannot open %s (%s)%s -- retrying every %.2gs"
                                    % (port, describe_exc(exc), (" -- " + hint) if hint else "", self.retry_interval))
            self.stop.wait(self.retry_interval)
            return
        # ---- connected
        self._fail_streak = 0
        self._last_note = (None, 0.0)
        self.marker("### %s %s" % ("reconnected" if self.connections else "connected", port))
        self.connections += 1
        self.state = "connected"
        try:
            self._read_loop(ser)
        finally:
            try:
                ser.close()
            except Exception:
                pass
        # Do not spin if the port flaps: give the OS a moment before reopening.
        self.stop.wait(self.retry_interval)

    def _read_loop(self, ser):
        connected_at = time.monotonic()
        got_data = False
        hinted = False
        while not self.stop.is_set():
            try:
                waiting = ser.in_waiting
                data = ser.read(waiting if waiting else 1)
            except (serial.SerialException, OSError, ValueError) as exc:
                item = self.assembler.flush()
                if item:
                    self.emit_line(*item)
                self.marker("### disconnected %s (%s)" % (self.port, describe_exc(exc)))
                self.state = "disconnected"
                return
            now = datetime.now()
            if data:
                got_data = True
                self.bytes_total += len(data)
                for ts, text in self.assembler.feed(data, now):
                    self.emit_line(ts, text)
            else:
                item = self.assembler.idle_flush(now, self.partial_timeout)
                if item:
                    self.emit_line(*item)
                if not got_data and not hinted and time.monotonic() - connected_at >= self.NO_DATA_HINT_S:
                    hinted = True
                    self.console.note(
                        self.label,
                        "%s is open but nothing was received for %ds. Wrong port? (A dongle with Studio + "
                        "logging has two COM ports; the Studio one stays silent.) Or the firmware was built "
                        "without the zmk-usb-logging snippet, or nothing is being logged right now."
                        % (self.port, int(self.NO_DATA_HINT_S)))


# --------------------------------------------------------------------------- MARK support

class MarkHub:
    """Numbers marks and writes each one, with ONE shared host timestamp, to every capture."""

    def __init__(self, captures, console):
        self.captures = captures
        self.console = console
        self._n = 0
        self._lock = threading.Lock()

    def mark(self, note=""):
        with self._lock:
            self._n += 1
            n = self._n
            ts = datetime.now()
            text = "### MARK %d%s" % (n, (" " + note) if note else "")
            for c in self.captures:
                c.sink.write(ts, text)
        self.console.note("", "MARK %d inserted at %s in: %s%s" % (
            n, fmt_ts(ts), ", ".join(c.label for c in self.captures), (" (%s)" % note) if note else ""))
        return n, ts


def stdin_mark_loop(stdin, hub, stop):
    """Runs in its own daemon thread: Enter = MARK, text + Enter = MARK with a note."""
    while not stop.is_set():
        try:
            line = stdin.readline()
        except Exception:
            break
        if line == "":
            hub.console.note("", "stdin closed: MARK by Enter is disabled (Ctrl+C still stops)")
            break
        hub.mark(line.strip())


# --------------------------------------------------------------------------- port selection

def _default_name(device):
    return sanitize_name(str(device).lower())


def resolve_targets(ports, names, records):
    """Return [(name, device)] from --port/--name (paired by position) or auto-selection."""
    if ports:
        if len(names) > len(ports):
            raise SelectionError("more --name (%d) than --port (%d); pair them by position, e.g. "
                                 "--port COM5 --name dongle --port COM7 --name right" % (len(names), len(ports)))
        out = []
        for i, p in enumerate(ports):
            dev = normalize_port(p)
            out.append((sanitize_name(names[i]) if i < len(names) else _default_name(dev), dev))
        return out
    wants = names or [None]
    cands = [r for r in records if is_candidate(r)]
    if not records:
        raise SelectionError("no serial ports found. Plug the board in with a DATA cable (charge-only "
                             "cables show nothing), make sure the firmware was built with the "
                             "zmk-usb-logging snippet, then run --list.")
    if len(wants) == 1 and len(cands) == 1:
        dev = cands[0]["device"]
        return [(sanitize_name(wants[0]) if wants[0] else _default_name(dev), dev)]
    raise SelectionError(
        "cannot auto-select a port: %d candidate(s) for %d capture(s). Pass --port explicitly.\n\n%s"
        % (len(cands), len(wants), render_port_table(records)))


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="capture_log.py",
        description="Capture ZMK/Zephyr USB CDC-ACM logs to timestamped files (several ports at once).",
        epilog="Example: py capture_log.py --port COM5 --name dongle --port COM7 --name right --mark")
    p.add_argument("--list", action="store_true", help="list serial ports (VID:PID, serial, description) and exit")
    p.add_argument("--port", action="append", default=[], metavar="COMx",
                   help="serial port; repeat for several ports (paired with --name by position). "
                        "Omit to auto-select the single ZMK/Zephyr port")
    p.add_argument("--name", action="append", default=[], metavar="LABEL",
                   help="label used in the file name and console prefix, e.g. dongle / right / left")
    p.add_argument("--outdir", default="logs", help="output directory (default ./logs)")
    p.add_argument("--baud", type=int, default=115200, help="ignored by USB CDC, harmless (default 115200)")
    p.add_argument("--mark", "--grep-mark", dest="grep_mark", action="store_true",
                   help="Enter in this console inserts '### MARK <n>' (same host time) into every log file; "
                        "text before Enter is added as a note")
    p.add_argument("--keep-ansi", action="store_true",
                   help="keep ANSI colour escapes (Zephyr colours warnings/errors by default; stripped otherwise)")
    p.add_argument("--quiet", action="store_true", help="do not echo device lines to the console")
    p.add_argument("--no-follow", action="store_true",
                   help="do not follow the device to a new COM number if the old one disappears")
    p.add_argument("--partial-timeout", type=float, default=2.0, metavar="SEC",
                   help="flush an unterminated line after this many idle seconds (0 = never; default 2)")
    p.add_argument("--retry-interval", type=float, default=0.25, metavar="SEC",
                   help="seconds between reopen attempts while the port is gone (default 0.25)")
    p.add_argument("--read-timeout", type=float, default=0.1, metavar="SEC", help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version="capture_log.py " + __version__)
    return p


def _make_console_safe():
    """Korean Windows consoles are cp949: never die on an unencodable character."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def main(argv=None, *, stdin=None, stop_event=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _make_console_safe()

    if args.baud <= 0:
        parser.error("--baud must be positive")
    if args.baud == 1200:
        parser.error("refusing 1200 baud: it is the 'touch' speed that makes some Arduino/Adafruit setups "
                     "reset into the bootloader")
    load_pyserial()
    records = list_records()

    if args.list:
        if records:
            print(render_port_table(records))
        else:
            print("No serial ports found. Plug the board in with a DATA cable and try again.")
        return EXIT_OK

    try:
        targets = resolve_targets(args.port, args.name, records)
    except SelectionError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_USAGE

    if len({d.upper() for _, d in targets}) != len(targets):
        sys.stderr.write("ERROR: the same port was given twice\n")
        return EXIT_USAGE
    seen = {}
    for name, dev in targets:
        if name.lower() in seen:
            sys.stderr.write("ERROR: duplicate --name %r (for %s and %s); names must be unique\n"
                             % (name, seen[name.lower()], dev))
            return EXIT_USAGE
        seen[name.lower()] = dev

    stop = stop_event if stop_event is not None else threading.Event()
    console = Console(show_lines=not args.quiet)
    try:
        outdir = os.path.abspath(args.outdir)
        start = datetime.now()
        by_device = {(r["device"] or "").upper(): r for r in records}

        captures = []
        try:
            for name, dev in targets:
                sink = LogSink(outdir, name, start)
                info = by_device.get(dev.upper())
                captures.append(Capture(
                    name, dev, sink, console, stop, baud=args.baud, strip_ansi=not args.keep_ansi,
                    partial_timeout=args.partial_timeout, retry_interval=args.retry_interval,
                    read_timeout=args.read_timeout, follow=not args.no_follow,
                    identity=identity_of(info) if info else None, port_info=info))
        except OSError as exc:
            for c in captures:
                c.sink.close()
            sys.stderr.write("ERROR: cannot create log file in %s: %s\n" % (outdir, exc))
            return EXIT_OUTPUT

        console.note("", "capture_log.py %s | Python %s | pyserial %s" % (
            __version__, sys.version.split()[0], getattr(serial, "VERSION", getattr(serial, "__version__", "?"))))
        for c in captures:
            console.note(c.label, "%s -> %s" % (c.port, c.sink.path))
        console.note("", "Ctrl+C stops and flushes.%s" % (
            " Press Enter to insert a MARK into every file (type text first to add a note)." if args.grep_mark else ""))

        for c in captures:
            c.start()
        if args.grep_mark:
            hub = MarkHub(captures, console)
            threading.Thread(target=stdin_mark_loop, args=(stdin if stdin is not None else sys.stdin, hub, stop),
                             name="stdin-mark", daemon=True).start()

        try:
            while not stop.is_set() and any(c.is_alive() for c in captures):
                stop.wait(0.2)
        except KeyboardInterrupt:
            console.note("", "Ctrl+C: stopping and flushing ...")
        finally:
            stop.set()
            for c in captures:
                try:
                    c.join(timeout=5.0)
                except KeyboardInterrupt:
                    pass
            for c in captures:  # no-op if the thread already closed it
                c.sink.close()

        console.note("", "done. Log files:")
        for c in captures:
            console.note("", "  %s  (%d connection(s); %s)" % (c.sink.path, c.connections, c.stats_text()))
        return EXIT_OK
    finally:
        console.close()  # print what is still queued, then stop the writer thread


if __name__ == "__main__":
    code = main()
    # A daemon thread may still be blocked in stdin.readline() (--mark); skip interpreter
    # finalisation so Windows cannot hang or abort on it. Everything is flushed/closed by now.
    def _flush():
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
    # Bounded: a stalled console must not keep the process alive after the logs are closed.
    _t = threading.Thread(target=_flush, daemon=True)
    _t.start()
    _t.join(2.0)
    os._exit(code)
