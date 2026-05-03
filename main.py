#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STABLE VIRTUAL TASK MANAGER v4.1 - Pure prompt_toolkit (no Rich, no ANSI clutter)
Correct widget: FormattedTextControl inside Window
pip install psutil prompt_toolkit
"""
import tracemalloc
tracemalloc.start()
import os
os.system("")

import sys
import signal
import threading
import time
from datetime import datetime
import sqlite3

import psutil

from prompt_toolkit.application import Application
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from prompt_toolkit.application.current import get_app
from prompt_toolkit.shortcuts import prompt as pt_prompt

# ---------- DATABASE ----------
class DatabaseManager:
    def __init__(self, db_name="metrics.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cur = self.conn.cursor()
        self._migrate()

    def _migrate(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                cpu REAL,
                memory REAL
            )
        """)
        self.conn.commit()
        for col, typ in [("disk_percent","REAL"),("net_sent","INTEGER"),("net_recv","INTEGER")]:
            try:
                self.cur.execute(f"SELECT {col} FROM system_metrics LIMIT 1")
            except sqlite3.OperationalError:
                self.cur.execute(f"ALTER TABLE system_metrics ADD COLUMN {col} {typ}")
                self.conn.commit()

    def log(self, cpu, mem, disk=0, sent=0, recv=0):
        try:
            self.cur.execute(
                "INSERT INTO system_metrics (timestamp,cpu,memory,disk_percent,net_sent,net_recv) VALUES (?,?,?,?,?,?)",
                (datetime.now().isoformat(), cpu, mem, disk, sent, recv)
            )
            self.conn.commit()
        except:
            pass

    def last_logs(self, n=10):
        try:
            return self.cur.execute(
                "SELECT timestamp,cpu,memory FROM system_metrics ORDER BY id DESC LIMIT ?",(n,)
            ).fetchall()
        except:
            return []

    def close(self):
        self.conn.close()

# ---------- STATE ----------
class State:
    def __init__(self):
        self.page = 0          # 0-proc, 1-sys, 2-net, 3-logs, 4-help
        self.filter = ""
        self.sort_by = "cpu"   # cpu, mem, name, pid
        self.cpu = 0.0
        self.mem = 0.0
        self.disk = 0.0
        self.nsent = 0
        self.nrecv = 0
        self.message = ""
        self.pages = ["PROCESSES", "SYSTEM", "NETWORK", "LOGS", "HELP"]

    def next_page(self):
        self.page = (self.page + 1) % len(self.pages)
    def prev_page(self):
        self.page = (self.page - 1) % len(self.pages)
    def toggle_sort(self):
        opts = ["cpu","mem","name","pid"]
        i = opts.index(self.sort_by)
        self.sort_by = opts[(i+1) % len(opts)]
    def set_filter(self, txt):
        self.filter = txt

# ---------- UI BUILDER (returns FormattedText) ----------
class UIBuilder:
    def __init__(self, state, db):
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
            "status": "blue",
            "header.proc": "bold cyan",
            "log.ts": "#666666",
            "log.val": "",
            "panel.border": "blue",
            "panel.system": "green",
            "panel.net": "magenta",
            "panel.log": "yellow",
            "panel.help": "yellow",
            "message": "bold yellow",
        })

    def render(self):
        """Возвращает FormattedText для отображения"""
        lines = []
        # header
        lines.append(("class:title", " STABLE TASK MANAGER v4.1 "))
        lines.append(("", "\n"))
        lines.append(("class:subtitle", f" Page: {self.s.pages[self.s.page]} "))
        lines.append(("class:sep", "\n" + "─"*60 + "\n\n"))

        # body
        body = self._body()
        lines.extend(body)

        # message
        if self.s.message:
            lines.append(("class:message", f"\n  {self.s.message}\n"))
            self.s.message = ""

        # footer
        lines.append(("class:footer", " ←→:nav  /:filter  r:reset  s:sort  k:kill  q:quit  F1:help "))
        return FormattedText(lines)

    def _body(self):
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

    def _bar(self, val, label, width=30):
        filled = int(val * width / 100)
        filled = min(filled, width)
        if val > 80:
            color = "bar.red"
        elif val > 50:
            color = "bar.yellow"
        else:
            color = "bar.green"
        bar = "█" * filled + "░" * (width - filled)
        return [("class:"+color, f"{label}: [{bar}] {val:5.1f}%")]

    def _render_procs(self):
        lines = [("class:header.proc", f"Processes  (sort by: {self.s.sort_by.upper()})"), ("", "\n")]
        lines.append(("", f"{'PID':<8}{'Name':<30}{'CPU %':>8}{'MEM %':>8}{'Status':>10}\n"))
        lines.append(("", "-"*70 + "\n"))

        procs = []
        try:
            for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent','status']):
                try:
                    info = p.info
                    name = info['name'] or "Unknown"
                    if self.s.filter and self.s.filter.lower() not in name.lower():
                        continue
                    procs.append({
                        'pid': info['pid'],
                        'name': name[:27]+"..." if len(name)>30 else name,
                        'cpu': info['cpu_percent'] or 0,
                        'mem': info['memory_percent'] or 0,
                        'status': info['status']
                    })
                except:
                    continue
        except:
            pass

        procs.sort(key=lambda x: x[self.s.sort_by], reverse=True)
        for p in procs[:100]:
            pid = f"{p['pid']:<8}"
            name = f"{p['name']:<30}"
            cpu = f"{p['cpu']:6.1f}  "
            mem = f"{p['mem']:6.2f}  "
            status = f"{p['status']:>10}\n"

            cpu_c = "cpu.green" if p['cpu']<20 else ("cpu.yellow" if p['cpu']<50 else "cpu.red")
            mem_c = "mem.green" if p['mem']<20 else ("mem.yellow" if p['mem']<50 else "mem.red")

            lines.append(("class:pid", pid))
            lines.append(("class:name", name))
            lines.append(("class:"+cpu_c, cpu))
            lines.append(("class:"+mem_c, mem))
            lines.append(("class:status", status))

        if self.s.filter:
            lines.append(("", f"\nFilter: '{self.s.filter}'  (r to reset)\n"))
        return lines

    def _render_system(self):
        lines = []
        lines.extend(self._bar(self.s.cpu, "CPU", 35))
        lines.append(("", "\n"))
        lines.extend(self._bar(self.s.mem, "RAM", 35))
        lines.append(("", f"\n\n  Disk: {self.s.disk:.1f}%      Network: ↑{self.s.nsent//1024}KB ↓{self.s.nrecv//1024}KB\n"))
        if self.s.filter:
            lines.append(("", f"  Filter: '{self.s.filter}'  (r to reset)\n"))
        return lines

    def _render_network(self):
        lines = [("", "Network connections (may require admin rights)\n\n")]
        try:
            conns = psutil.net_connections()
            listen = [c for c in conns if c.status=='LISTEN']
            lines.append(("", f"{'Type':<8}{'Local Address':<40}{'PID':>8}\n"))
            lines.append(("", "-"*56 + "\n"))
            for c in listen[:20]:
                addr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "N/A"
                pid = str(c.pid) if c.pid else "N/A"
                lines.append(("", f"{'TCP':<8}{addr:<40}{pid:>8}\n"))
        except:
            lines.append(("class:bar.red", "Could not retrieve network data.\n"))
        return lines

    def _render_logs(self):
        logs = self.db.last_logs(10)
        lines = [("", "System logs (last 10 records)\n\n")]
        if not logs:
            lines.append(("", "No data yet...\n"))
        else:
            lines.append(("", f"{'Timestamp':<20}{'CPU %':>8}{'MEM %':>8}\n"))
            lines.append(("", "-"*40 + "\n"))
            for ts, cpu, mem in logs:
                cpu_c = "log.val red" if cpu and cpu>50 else "log.val green"
                mem_c = "log.val red" if mem and mem>50 else "log.val green"
                lines.append(("class:log.ts", f"{ts[:19] if ts else '':20}"))
                lines.append(("class:"+cpu_c, f"{cpu:5.1f}   " if cpu else "     "))
                lines.append(("class:"+mem_c, f"{mem:5.1f}\n" if mem else "     \n"))
        return lines

    def _render_help(self):
        return [("", """
  KEYS
  ← →  Switch pages    / Filter processes
  r    Reset filter    s Change sort
  k    Kill process    q Quit
  F1   This help

  Pages: PROCESSES | SYSTEM | NETWORK | LOGS
  Colors: green=low, yellow=mid, red=high
""")]

# ---------- APPLICATION ----------
class TaskManagerApp:
    def __init__(self):
        self.state = State()
        self.db = DatabaseManager()
        self.ui = UIBuilder(self.state, self.db)

        # Виджет, который принимает FormattedText
        self.main_content = FormattedTextControl(text="Loading...")
        self.window = Window(content=self.main_content, style="class:text")

        self.kb = self._keybindings()
        self.app = Application(
            layout=Layout(HSplit([self.window])),
            key_bindings=self.kb,
            full_screen=True,
            style=self.ui.style,
        )
        self.running = True
        signal.signal(signal.SIGINT, self._sig)
        signal.signal(signal.SIGTERM, self._sig)

    def _sig(self, signum, frame):
        self.running = False
        self.db.close()
        sys.exit(0)

    def _keybindings(self):
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
            event.app.exit()
        @kb.add("/")
        def _(event):
            try:
                res = pt_prompt("Filter: ", default=self.state.filter)
                self.state.set_filter(res)
            except:
                pass
            event.app.invalidate()
        @kb.add("r")
        def _(event):
            self.state.set_filter("")
            event.app.invalidate()
        @kb.add("s")
        def _(event):
            self.state.toggle_sort()
            event.app.invalidate()
        @kb.add("k")
        def _(event):
            try:
                pid_str = pt_prompt("Kill PID: ")
                pid = int(pid_str)
                p = psutil.Process(pid)
                name = p.name()
                p.terminate()
                self.state.message = f"OK: terminated PID {pid} ({name})"
            except ValueError:
                self.state.message = "Invalid PID"
            except psutil.NoSuchProcess:
                self.state.message = "Process not found"
            except psutil.AccessDenied:
                self.state.message = "Access denied (admin?)"
            except Exception as e:
                self.state.message = str(e)
            event.app.invalidate()
        @kb.add("f1")
        def _(event):
            self.state.page = 4
            event.app.invalidate()
        return kb

    def _update_loop(self):
        time.sleep(0.2)
        while self.running:
            try:
                self.state.cpu = psutil.cpu_percent()
                self.state.mem = psutil.virtual_memory().percent
            except:
                pass
            try:
                self.state.disk = psutil.disk_usage('/').percent
            except:
                self.state.disk = 0
            try:
                net = psutil.net_io_counters()
                self.state.nsent = net.bytes_sent
                self.state.nrecv = net.bytes_recv
            except:
                self.state.nsent = 0
                self.state.nrecv = 0

            self.db.log(self.state.cpu, self.state.mem, self.state.disk, self.state.nsent, self.state.nrecv)

            ft = self.ui.render()
            self.main_content.text = ft  # Теперь это работает, т.к. FormattedTextControl ожидает FormattedText

            try:
                get_app().invalidate()
            except:
                pass
            time.sleep(1)

    def run(self):
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()
        self.app.run()

if __name__ == "__main__":
    print("Starting Task Manager v4.1 (pure prompt_toolkit, no ANSI clutter)...")
    time.sleep(0.8)
    TaskManagerApp().run()