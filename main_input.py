#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Terminal version with input() for compatibility"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import time
import psutil
import signal
import os
import threading
from threading import Thread

def handler(sig, frame):
    print("\n\nDone.")
    sys.exit(0)

signal.signal(signal.SIGINT, handler)

scroll_offset = 0
lines_per_page = 12
filter_text = ""
last_cmd = ""

print("STABLE TASK MANAGER v5.0")
print("="*55)

while True:
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    boot = psutil.boot_time()
    uptime = int(time.time() - boot)
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    mins = (uptime % 3600) // 60
    
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except:
        pass
    
    print("\n" + "=" * 55)
    print(f" STABLE TASK MANAGER v5.0")
    print("=" * 55)
    print(f" {time.strftime('%H:%M:%S')} | CPU:{cpu:5.1f}% MEM:{mem.percent:5.1f}% DISK:{disk.percent:5.1f}%")
    print(f" Uptime: {days}d {hours:02d}:{mins:02d}")
    print(f" Net: UP {net.bytes_sent//1024}KB DOWN {net.bytes_recv//1024}KB")
    print("-" * 55)
    
    procs = []
    for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent']):
        try:
            info = p.info
            if filter_text and filter_text.lower() not in (info['name'] or '').lower():
                continue
            procs.append(info)
        except:
            pass
    procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
    
    total = len(procs)
    start = scroll_offset
    end = scroll_offset + lines_per_page
    visible = procs[start:end]
    
    if filter_text:
        print(f" Filter: {filter_text}")
    
    print("-" * 55)
    
    for i, p in enumerate(visible, start + 1):
        name = (p['name'] or '?')[:22]
        pid = p['pid']
        cpu_val = p['cpu_percent']
        mem_val = p['memory_percent']
        print(f" {i:>3}. {name:<22} PID:{pid:<6} CPU:{cpu_val:5.1f}% MEM:{mem_val:5.1f}%")
    
    print("=" * 55)
    print(f" Showing {start+1}-{min(end, total)} of {total} processes")
    print(f" /search text  k PID  w/s scroll  r reset  q quit")
    print("=" * 55)
    
    cmd = input("Command: ").strip()
    
    if cmd:
        if cmd == 'q':
            print("Quitting...")
            break
        elif cmd == 'r':
            scroll_offset = 0
            filter_text = ""
        elif cmd.startswith('/'):
            filter_text = cmd[1:].strip()
            scroll_offset = 0
        elif cmd.startswith('k '):
            try:
                pid = int(cmd[2:].strip())
                p = psutil.Process(pid)
                name = p.name()
                p.terminate()
                print(f"[OK] Killed PID {pid} ({name})")
                time.sleep(1)
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(1)
        elif cmd == 'w':
            scroll_offset = max(0, scroll_offset - lines_per_page)
        elif cmd == 's':
            scroll_offset += lines_per_page
        elif cmd.isdigit():
            try:
                pid = int(cmd)
                p = psutil.Process(pid)
                name = p.name()
                p.terminate()
                print(f"[OK] Killed PID {pid} ({name})")
                time.sleep(1)
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(1)