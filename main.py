#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STABLE TASK MANAGER v5.0 - Enhanced with PID search, multi-sort, kill confirmation, 
system details (uptime, memory), disk I/O, network filters, CSV export, logs cleanup
pip install psutil prompt_toolkit

NOTE: Run this in Windows cmd.exe or PowerShell, not in Git Bash or similar.
"""
from __future__ import annotations

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import signal
import threading
import time
import logging
import json
from datetime import datetime
from pathlib import Path

import psutil
import msvcrt

from prompt_toolkit.application import Application
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from prompt_toolkit.application.current import get_app
from prompt_toolkit.shortcuts import prompt as pt_prompt
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput

CONFIG_FILE = Path(__file__).parent / "config.json"
LOG_FILE = Path(__file__).parent / "task_manager.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    defaults = {
        "refresh_interval": 1,
        "max_procs": 100,
        "history_size": 60,
        "log_retention_days": 7,
    }
    if CONFIG_FILE.exists():
        try:
            return {**defaults, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return defaults


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


CONFIG = load_config()


class DatabaseManager:
    def __init__(self, db_name: str = "metrics.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._migrate()

    def _migrate(self) -> None:
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                cpu REAL,
                memory REAL
            )
        """)
        self.conn.commit()
        for col, typ in [("disk_percent", "REAL"), ("net_sent", "INTEGER"), ("net_recv", "INTEGER")]:
            try:
                self.cur.execute(f"SELECT {col} FROM system_metrics LIMIT 1")
            except sqlite3.OperationalError:
                self.cur.execute(f"ALTER TABLE system_metrics ADD COLUMN {col} {typ}")
                self.conn.commit()

    def log(self, cpu: float, mem: float, disk: float = 0, sent: int = 0, recv: int = 0) -> None:
        try:
            self.cur.execute(
                "INSERT INTO system_metrics (timestamp,cpu,memory,disk_percent,net_sent,net_recv) VALUES (?,?,?,?,?,?)",
                (datetime.now().isoformat(), cpu, mem, disk, sent, recv)
            )
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")

    def last_logs(self, n: int = 10) -> list:
        try:
            return self.cur.execute(
                "SELECT timestamp,cpu,memory,disk_percent,net_sent,net_recv FROM system_metrics ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        except Exception:
            return []

    def get_history(self, n: int = 60) -> list:
        try:
            return self.cur.execute(
                "SELECT timestamp,cpu,memory FROM system_metrics ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        except Exception:
            return []

    def export_csv(self, filename: str, limit: int = 1000) -> bool:
        try:
            rows = self.cur.execute(
                "SELECT * FROM system_metrics ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            if not rows:
                return False
            with open(filename, "w", encoding="utf-8") as f:
                f.write("timestamp,cpu,memory,disk_percent,net_sent,net_recv\n")
                for r in rows:
                    f.write(f"{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}\n")
            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False

    def cleanup(self, days: int = 7) -> int:
        try:
            cutoff = datetime.now().timestamp() - (days * 86400)
            self.cur.execute("DELETE FROM system_metrics WHERE id IN (SELECT id FROM system_metrics WHERE timestamp < datetime(?))", (cutoff,))
            deleted = self.cur.rowcount
            self.conn.commit()
            return deleted
        except Exception:
            return 0

    def close(self) -> None:
        self.conn.close()


import sqlite3


class State:
    def __init__(self):
        self.page = 0
        self.filter = ""
        self.filter_type = "name"  # name, pid, port
        self.sort_by = "cpu"
        self.sort_asc = False
        self.cpu = 0.0
        self.mem = 0.0
        self.disk = 0.0
        self.nsent = 0
        self.nrecv = 0
        self.message = ""
        self.confirm_kill = False
        self.kill_tree = False
        self.uptime = 0
        self.mem_used = 0
        self.mem_available = 0
        self.cpu_count = 0
        self.history = []
        self.pages = ["PROCESSES", "SYSTEM", "NETWORK", "LOGS", "HELP"]
        self.scroll_offset = 0
        self.lines_per_page = 15

    def next_page(self) -> None:
        self.page = (self.page + 1) % len(self.pages)

    def prev_page(self) -> None:
        self.page = (self.page - 1) % len(self.pages)

    def toggle_sort(self) -> None:
        opts = ["cpu", "mem", "name", "pid"]
        if self.sort_by not in opts:
            self.sort_by = "cpu"
            return
        i = opts.index(self.sort_by)
        self.sort_by = opts[(i + 1) % len(opts)]

    def toggle_sort_dir(self) -> None:
        self.sort_asc = not self.sort_asc

    def set_filter(self, txt: str, ftype: str = "name") -> None:
        self.filter = txt
        self.filter_type = ftype


class UIBuilder:
    def __init__(self, state: State, db: DatabaseManager):
        self.s = state
        self.db = db
        self.style = Style.from_dict({
            "title": "bold white bg:#0000aa",
            "subtitle": "bold yellow",
            "sep": "#888888",
            "footer": "reverse",
            "bar.green": "green",
            "bar.yellow": "yellow",
            "bar.red": "red",
            "pid": "#aaaaaa",
            "name": "green",
            "cpu.green": "green",
            "cpu.yellow": "yellow",
            "cpu.red": "red",
            "mem.green": "green",
            "mem.yellow": "yellow",
            "mem.red": "red",
            "disk.green": "green",
            "disk.yellow": "yellow",
            "disk.red": "red",
            "status": "blue",
            "header.proc": "bold cyan",
            "log.ts": "#666666",
            "log.val": "",
            "panel.border": "blue",
            "panel.system": "green",
            "panel.net": "magenta",
            "panel.log": "yellow",
            "panel.help": "yellow",
            "panel.warning": "bold yellow",
            "message": "bold yellow",
            "key.hint": "bold #00aaaa",
        })

    def render(self) -> FormattedText:
        lines = []
        lines.append(("class:title", " STABLE TASK MANAGER v5.0 "))
        lines.append(("", "\n"))
        lines.append(("class:subtitle", f" Page: {self.s.pages[self.s.page]} "))
        lines.append(("class:sep", "\n" + "─" * 60 + "\n\n"))

        body = self._body()
        lines.extend(body)

        if self.s.message:
            lines.append(("class:message", f"\n  {self.s.message}\n"))
            self.s.message = ""

        lines.extend(self._footer())
        return FormattedText(lines)

    def _body(self) -> list:
        page = self.s.page
        if page == 0:
            return self._render_procs()
        elif page == 1:
            return self._render_system()
        elif page == 2:
            return self._render_network()
        elif page == 3:
            return self._render_logs()
        else:
            return self._render_help()

    def _footer(self) -> list:
        page = self.s.page
        if page == 0:
            ft = f"{self.s.filter_type}:{self.s.filter}" if self.s.filter else "no filter"
            sort_dir = "↑" if self.s.sort_asc else "↓"
            return [("class:footer", f" ←→:nav  /:name  N:pid  r:reset  s:sort {sort_dir}  k:kill  K:kill+  q:quit  F1:help\n"),
                    ( "", f"  Filter: {ft}  Sort: {self.s.sort_by.upper()}  Procs: {CONFIG['max_procs']}  Interval: {CONFIG['refresh_interval']}s\n")]
        elif page == 1:
            return [("class:footer", " ←→:nav  c:clear logs  e:export  d:del old  q:quit  F1:help\n")]
        elif page == 2:
            return [("class:footer", " ←→:nav  /:port filter  a:all conns  r:reset  q:quit  F1:help\n")]
        elif page == 3:
            return [("class:footer", " ←→:nav  e:export CSV  c:cleanup  q:quit  F1:help\n")]
        else:
            return [("class:footer", " q:quit ")]

    def _bar(self, val: float, label: str, width: int = 30) -> list:
        filled = int(val * width / 100)
        filled = min(filled, width)
        if val > 80:
            color = "bar.red"
        elif val > 50:
            color = "bar.yellow"
        else:
            color = "bar.green"
        bar = "█" * filled + "░" * (width - filled)
        return [("class:" + color, f"{label}: [{bar}] {val:5.1f}%")]

    def _render_procs(self) -> list:
        sort_indicator = "↑" if self.s.sort_asc else "↓"
        lines = [("class:header.proc", f"Processes  (sort: {self.s.sort_by.upper()}{sort_indicator})"), ("", "\n")]
        lines.append(("", f"{'PID':<8}{'Name':<25}{'CPU %':>7}{'MEM %':>7}{'DiskIO':>12}{'Status':>10}\n"))
        lines.append(("", "-" * 74 + "\n"))

        procs = []
        try:
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'io_counters']):
                try:
                    info = p.info
                    name = info['name'] or "Unknown"

                    if self.s.filter:
                        if self.s.filter_type == "pid":
                            if self.s.filter not in str(info['pid']):
                                continue
                        elif self.s.filter_type == "name":
                            if self.s.filter.lower() not in name.lower():
                                continue
                        else:
                            if self.s.filter.lower() not in name.lower():
                                continue

                    try:
                        io = info.get('io_counters')
                        disk_io = f"{io.read_bytes + io.write_bytes}" if io and hasattr(io, 'read_bytes') else "0"
                        if io:
                            disk_val = (io.read_bytes + io.write_bytes) / (1024 * 1024)
                            disk_io = f"{disk_val:.1f}M"
                    except Exception:
                        disk_io = "0"

                    procs.append({
                        'pid': info['pid'],
                        'name': name[:22] + "..." if len(name) > 25 else name,
                        'cpu': info['cpu_percent'] or 0,
                        'mem': info['memory_percent'] or 0,
                        'disk': disk_io,
                        'status': info['status']
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        procs.sort(key=lambda x: x[self.s.sort_by], reverse=not self.s.sort_asc)

        for p in procs[:CONFIG['max_procs']]:
            pid = f"{p['pid']:<8}"
            name = f"{p['name']:<25}"
            cpu = f"{p['cpu']:6.1f} "
            mem = f"{p['mem']:6.2f} "
            disk = f"{p['disk']:>10} "
            status = f"{p['status']:>10}\n"

            cpu_c = "cpu.green" if p['cpu'] < 20 else ("cpu.yellow" if p['cpu'] < 50 else "cpu.red")
            mem_c = "mem.green" if p['mem'] < 20 else ("mem.yellow" if p['mem'] < 50 else "mem.red")

            lines.append(("class:pid", pid))
            lines.append(("class:name", name))
            lines.append(("class:" + cpu_c, cpu))
            lines.append(("class:" + mem_c, mem))
            lines.append(("class:disk.yellow" if p['disk'] != "0" else "class:disk.green", disk))
            lines.append(("class:status", status))

        if self.s.filter:
            lines.append(("", f"\nFilter: '{self.s.filter}' ({self.s.filter_type}) - press r to reset\n"))
        return lines

    def _render_system(self) -> list:
        lines = []
        lines.extend(self._bar(self.s.cpu, "CPU", 35))
        lines.append(("", "\n"))
        lines.extend(self._bar(self.s.mem, "RAM", 35))
        lines.append(("", "\n"))
        lines.extend(self._bar(self.s.disk, "DISK", 35))

        secs = int(self.s.uptime)
        days = secs // 86400
        hours = (secs % 86400) // 3600
        mins = (secs % 3600) // 60
        uptime_str = f"{days}d {hours:h02d}:{mins:02d}"

        mem_used_gb = self.s.mem_used / (1024 ** 3)
        mem_avail_gb = self.s.mem_available / (1024 ** 3)

        lines.append(("", "\n"))
        lines.append(("", f"  Memory: {mem_used_gb:.1f}G used / {mem_avail_gb:.1f}G available\n"))
        lines.append(("", f"  Disk: {self.s.disk:.1f}% used\n"))
        lines.append(("", f"  Network: ↑{self.s.nsent // 1024}KB ↓{self.s.nrecv // 1024}KB\n"))
        lines.append(("", f"  Uptime: {uptime_str}\n"))
        lines.append(("", f"  CPU cores: {self.s.cpu_count}\n"))

        history = self.s.history
        if history and len(history) >= 2:
            lines.append(("", "\n  CPU History (last 30): \n  "))
            hist_cpu = [h[1] or 0 for h in history[-30:]]
            chart_height = 5
            for level in range(chart_height, 0, -1):
                row = []
                for val in hist_cpu:
                    threshold = level * 20
                    row.append("█" if val >= threshold else " ")
                lines.append(("", "  " + "".join(row) + f" {level * 20}%\n"))
            lines.append(("", "  " + "_" * 30 + "\n"))

        if self.s.filter:
            lines.append(("", f"  Filter: '{self.s.filter}'  (r to reset)\n"))

        lines.append(("", f"\n  History records: {len(history)}\n"))
        return lines

    def _render_network(self) -> list:
        show_all = getattr(self.s, 'show_all_conns', False)
        lines = [("", f"Network connections (press a to toggle all: {'ON' if show_all else 'LISTEN only'})\n\n")]

        try:
            conns = psutil.net_connections()
            if not show_all:
                conns = [c for c in conns if c.status == 'LISTEN']

            if self.s.filter:
                conns = [c for c in conns if self.s.filter in str(c.laddr.port) if c.laddr]

            lines.append(("", f"{'Type':<6}{'Status':<12}{'Local Address':<40}{'PID':>8}\n"))
            lines.append(("", "-" * 70 + "\n"))
            for c in conns[:40]:
                addr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "N/A"
                pid = str(c.pid) if c.pid else "-"
                status = c.status or "-"
                lines.append(("", f"{'TCP' if c.type == 1 else 'UDP':<6}{status:<12}{addr:<40}{pid:>8}\n"))
        except psutil.AccessDenied:
            lines.append(("class:bar.red", "Need admin rights to view connections.\n"))
        except Exception as e:
            lines.append(("class:bar.red", f"Error: {e}\n"))

        if self.s.filter:
            lines.append(("", f"\nFilter (port): '{self.s.filter}'  (r to reset)\n"))
        return lines

    def _render_logs(self) -> list:
        logs = self.db.last_logs(15)
        lines = [("class:panel.log", "System logs (last 15 records)\n\n")]

        if not logs:
            lines.append(("", "No data yet...\n"))
        else:
            lines.append(("", f"{'Timestamp':<22}{'CPU %':>8}{'MEM %':>8}{'Disk%':>8}{'Net↑':>10}{'Net↓':>10}\n"))
            lines.append(("", "-" * 70 + "\n"))
            for r in logs:
                ts = r[0][:19] if r[0] else ""
                cpu = r[1] or 0
                mem = r[2] or 0
                disk = r[3] or 0
                net_s = r[4] // 1024 if r[4] else 0
                net_r = r[5] // 1024 if r[5] else 0
                cpu_c = "log.val red" if cpu > 50 else "log.val green"
                mem_c = "log.val red" if mem > 50 else "log.val green"
                lines.append(("class:log.ts", f"{ts:<22}"))
                lines.append(("class:" + cpu_c, f"{cpu:7.1f} "))
                lines.append(("class:" + mem_c, f"{mem:7.1f} "))
                lines.append(("", f"{disk:7.1f} "))
                lines.append(("", f"{net_s:9}K "))
                lines.append(("", f"{net_r:9}K\n"))
        return lines

    def _render_help(self) -> list:
        return [("", """
  STABLE TASK MANAGER v5.0 - Help

  NAVIGATION
    ← →      Switch pages
    F1       This help page

  PROCESSES PAGE
    /        Filter by name
    N        Filter by PID
    r        Reset filter
    s        Toggle sort (cpu → mem → name → pid)
    Space    Toggle sort direction (asc/desc)
    k        Kill process (with confirm)
    K        Kill process tree (with confirm)
    Enter    Select process to view details

  SYSTEM PAGE
    c        Clear old logs (older than retention)
    e        Export logs to CSV
    d        Delete logs older than N days

  NETWORK PAGE
    /        Filter by port number
    a        Toggle show all connections
    r        Reset filter

  LOGS PAGE
    e        Export to CSV
    c        Cleanup old records

  CONFIG
    Config file: config.json
    Edit manually or defaults are used

  COLORS
    Green  = Low usage (< 20%)
    Yellow = Medium (20-50%)
    Red    = High (> 50%)
""")]


class TaskManagerApp:
    def __init__(self):
        self.state = State()
        self.db = DatabaseManager()
        self.ui = UIBuilder(self.state, self.db)

        self.main_content = FormattedTextControl(text="Loading...")
        self.window = Window(content=self.main_content, style="class:text")

        self.kb = self._keybindings()

        try:
            self.app = Application(
                layout=Layout(HSplit([self.window])),
                key_bindings=self.kb,
                full_screen=True,
                style=self.ui.style,
            )
        except Exception:
            print("\n" + "="*60)
            print("STABLE TASK MANAGER v5.0")
            print("="*60)
            print("Note: Run in Windows Terminal or cmd.exe for full UI")
            print("     VS Code terminal may not support full-screen apps")
            print("="*60 + "\n")
            print("System initialized. Check network, CPU, memory...")
            print("Press Ctrl+C to quit")
            self.app = None
        self.running = True
        signal.signal(signal.SIGINT, self._sig)
        signal.signal(signal.SIGTERM, self._sig)
        logger.info("Task Manager v5.0 started")

    def _sig(self, signum: int, frame) -> None:
        self.running = False
        self.db.close()
        logger.info("Task Manager shutting down")
        sys.exit(0)

    def _keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("right")
        def _(event):
            self.state.next_page()
            event.app.invalidate()

        @kb.add("left")
        def _(event):
            self.state.prev_page()
            event.app.invalidate()

        @kb.add("q")
        def _(event):
            self.running = False
            self.db.close()
            logger.info("User quit")
            event.app.exit()

        @kb.add("/")
        def _(event):
            if self.state.page == 2:
                self.state.filter_type = "port"
            else:
                self.state.filter_type = "name"
            try:
                res = pt_prompt(f"Filter ({self.state.filter_type}): ", default=self.state.filter)
                self.state.set_filter(res, self.state.filter_type)
            except Exception:
                pass
            event.app.invalidate()

        @kb.add("n")
        def _(event):
            self.state.filter_type = "pid"
            if self.state.page == 0:
                try:
                    res = pt_prompt("Filter by PID: ", default=self.state.filter)
                    self.state.set_filter(res, "pid")
                except Exception:
                    pass
            event.app.invalidate()

        @kb.add("r")
        def _(event):
            self.state.filter = ""
            self.state.set_filter("")
            event.app.invalidate()

        @kb.add("s")
        def _(event):
            self.state.toggle_sort()
            event.app.invalidate()

        @kb.add(" ")
        def _(event):
            if self.state.page == 0:
                self.state.toggle_sort_dir()
            event.app.invalidate()

        @kb.add("k")
        def _(event):
            if not self.state.confirm_kill:
                self.state.message = "Press k again to confirm kill, or K for kill-tree"
                self.state.confirm_kill = True
                event.app.invalidate()
                return

            try:
                pid_str = pt_prompt("Kill PID: ")
                pid = int(pid_str)
                p = psutil.Process(pid)
                name = p.name()
                p.terminate()
                self.state.message = f"OK: terminated PID {pid} ({name})"
                logger.info(f"Killed process {pid} ({name})")
            except ValueError:
                self.state.message = "Invalid PID"
            except psutil.NoSuchProcess:
                self.state.message = "Process not found"
            except psutil.AccessDenied:
                self.state.message = "Access denied (admin?)"
            except Exception as e:
                self.state.message = str(e)
            self.state.confirm_kill = False
            event.app.invalidate()

        @kb.add("K")
        def _(event):
            try:
                pid_str = pt_prompt("Kill PID (tree): ")
                pid = int(pid_str)
                parent = psutil.Process(pid)
                name = parent.name()
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                parent.terminate()
                self.state.message = f"Killed tree: {name} (PID {pid})"
                logger.info(f"Killed process tree {pid} ({name})")
            except ValueError:
                self.state.message = "Invalid PID"
            except psutil.NoSuchProcess:
                self.state.message = "Process not found"
            except psutil.AccessDenied:
                self.state.message = "Access denied (admin?)"
            except Exception as e:
                self.state.message = str(e)
            event.app.invalidate()

        @kb.add("a")
        def _(event):
            if self.state.page == 2:
                self.state.show_all_conns = not getattr(self.state, 'show_all_conns', False)
            event.app.invalidate()

        @kb.add("e")
        def _(event):
            if self.state.page in (1, 3):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"metrics_{ts}.csv"
                if self.state.db.export_csv(filename):
                    self.state.message = f"Exported to {filename}"
                    logger.info(f"Exported logs to {filename}")
                else:
                    self.state.message = "Export failed"
            event.app.invalidate()

        @kb.add("c")
        def _(event):
            if self.state.page == 1:
                days = CONFIG.get("log_retention_days", 7)
                deleted = self.state.db.cleanup(days)
                self.state.message = f"Deleted {deleted} old records"
                logger.info(f"Cleaned up {deleted} old log records")
            event.app.invalidate()

        @kb.add("d")
        def _(event):
            if self.state.page == 1:
                try:
                    days_str = pt_prompt("Delete logs older than (days): ", default="7")
                    days = int(days_str)
                    deleted = self.state.db.cleanup(days)
                    self.state.message = f"Deleted {deleted} records older than {days} days"
                    logger.info(f"Cleaned up {deleted} logs older than {days} days")
                except ValueError:
                    self.state.message = "Invalid number"
            event.app.invalidate()

        @kb.add("f1")
        def _(event):
            self.state.page = 4
            event.app.invalidate()

        return kb

    def _update_loop(self) -> None:
        time.sleep(0.2)
        while self.running:
            try:
                self.state.cpu = psutil.cpu_percent()
                vm = psutil.virtual_memory()
                self.state.mem = vm.percent
                self.state.mem_used = vm.used
                self.state.mem_available = vm.available
                self.state.cpu_count = psutil.cpu_count()
            except Exception:
                pass

            try:
                self.state.disk = psutil.disk_usage('/').percent
            except Exception:
                self.state.disk = 0

            try:
                net = psutil.net_io_counters()
                self.state.nsent = net.bytes_sent
                self.state.nrecv = net.bytes_recv
            except Exception:
                self.state.nsent = 0
                self.state.nrecv = 0

            try:
                boot_time = psutil.boot_time()
                self.state.uptime = time.time() - boot_time
            except Exception:
                self.state.uptime = 0

            self.db.log(self.state.cpu, self.state.mem, self.state.disk, self.state.nsent, self.state.nrecv)
            self.state.history = self.db.get_history(CONFIG.get("history_size", 60))

            try:
                ft = self.ui.render()
                self.main_content.text = ft
            except Exception:
                pass

            try:
                get_app().invalidate()
            except Exception:
                pass

            time.sleep(CONFIG.get("refresh_interval", 1))

    def run(self) -> None:
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()
        if self.app:
            self.app.run()
        else:
            self._run_terminal_mode()

    def _run_terminal_mode(self) -> None:
        """Fallback terminal mode for environments without full UI support"""
        import threading

        input_running = True
        if os.name == 'nt':
            def input_listener():
                try:
                    while input_running and self.running:
                        if msvcrt.kbhit():
                            key = msvcrt.getch()
                            if key in (b'w', b'W', b'\xe0'):
                                self.state.scroll_offset = max(0, self.state.scroll_offset - 1)
                            elif key in (b's', b'S'):
                                self.state.scroll_offset += 1
                            elif key in (b'q', b'Q'):
                                self.running = False
                            elif key in (b'r', b'R'):
                                self.state.scroll_offset = 0
                except Exception:
                    pass
            t = threading.Thread(target=input_listener, daemon=True)
            t.start()

        scroll_counter = 0
        try:
            self._print_status()
            print("\n  Auto-scrolling every 5s. Press q to quit\n")
            while self.running:
                time.sleep(CONFIG.get("refresh_interval", 1))

                scroll_counter += 1
                if scroll_counter >= 5:
                    scroll_counter = 0
                    self.state.scroll_offset += self.state.lines_per_page

                self._print_status()
        except KeyboardInterrupt:
            print("\nQuitting...")
        finally:
            input_running = False
            self._sig(0, None)

def _print_status(self) -> None:
        """Print status in terminal fallback mode"""
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
        except Exception:
            print("\n" + "="*60)
        
        cpu = self.state.cpu
        mem = self.state.mem
        disk = self.state.disk
        
        def bar(val, w=30):
            f = int(val * w / 100)
            c = '#' * f + '-' * (w - f)
            return f"[{c}] {val:.1f}%"
        
        vm = psutil.virtual_memory()
        
        print(f"\n{'='*60}")
        print(f"  STABLE TASK MANAGER v5.0 (Terminal Mode)")
        print(f"{'='*60}\n")
        
        print(f"  CPU:  {bar(cpu, 35)}")
        print(f"  RAM:  {bar(mem, 35)}  ({vm.used//(1024**3):.1f}G / {vm.total//(1024**3):.1f}G)")
        print(f"  Disk: {bar(disk, 35)}")
        
        print(f"\n  Network: Up {self.state.nsent//1024}KB  Down {self.state.nrecv//1024}KB")
        
        boot = psutil.boot_time()
        uptime = int(time.time() - boot)
        days, rem = divmod(uptime, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        print(f"  Uptime: {days}d {hours:02d}:{mins:02d}")
        print(f"  CPU cores: {self.state.cpu_count}")
        
        print(f"\n  Top processes by CPU:")
        
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                if p.info['name']:
                    procs.append(p.info)
            except:
                pass
        procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        
        offset = self.state.scroll_offset
        limit = self.state.lines_per_page
        visible = procs[offset:offset + limit]
        
        for i, p in enumerate(visible, offset + 1):
            print(f"    {i}. PID:{p['pid']} {p['name'][:20]:<20} CPU:{p.get('cpu_percent', 0):>5.1f}% MEM:{p.get('memory_percent', 0):>5.1f}%")
        
        total = len(procs)
        start = offset + 1
        end = min(offset + limit, total)
        print(f"\n  Showing {start}-{end} of {total} processes")
        print(f"  Arrow UP/DOWN to scroll, q to quit")
        
        print(f"\n{'-'*60}")
        print("  q:quit  w/s:scroll  Ctrl+C:quit  (Limited mode)")
        print(f"  Logs: {len(self.state.history)} records\n")


if __name__ == "__main__":
    print("Starting Task Manager v5.0...")
    logger.info("Starting Task Manager v5.0")
    time.sleep(0.8)
    TaskManagerApp().run()