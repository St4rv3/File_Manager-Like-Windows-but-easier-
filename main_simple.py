#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STABLE TASK MANAGER v5.0 - Terminal version for limited terminals
"""
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import signal
import time
import psutil

def signal_handler(sig, frame):
    print("\n\nShutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

print("=" * 60)
print("  STABLE TASK MANAGER v5.0")
print("=" * 60)
print("  Starting monitor...")
print("  Press Ctrl+C to quit")
print("=" * 60)

def get_uptime():
    try:
        boot = psutil.boot_time()
        secs = int(time.time() - boot)
        d, h = divmod(secs, 86400)
        h, m = divmod(h, 3600)
        return f"{d}d {h:02d}:{m:02d}"
    except Exception:
        return "?"

print("\n" + "="*60)
print("  SYSTEM METRICS")
print("="*60)

while True:
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    
    # Simple progress bars
    cpu_bar = "#" * int(cpu/3.3) + "-" * (30 - int(cpu/3.3))
    mem_bar = "#" * int(mem.percent/3.3) + "-" * (30 - int(mem.percent/3.3))
    disk_bar = "#" * int(disk.percent/3.3) + "-" * (30 - int(disk.percent/3.3))
    
    print(f"""
------------------------------------------------------------
TIME: {time.strftime("%H:%M:%S")}

CPU:    [{cpu_bar}] {cpu:5.1f}%
MEM:    [{mem_bar}] {mem.percent:5.1f}%  ({mem.used//(1024**3):.1f}G / {mem.total//(1024**3):.1f}G)
DISK:   [{disk_bar}] {disk.percent:5.1f}% used

NET:    Up: {net.bytes_sent//1024:>6} KB   Down: {net.bytes_recv//1024:>6} KB
UPTIME: {get_uptime()}
CORES:  {psutil.cpu_count()}

------------------------------------------------------------
TOP PROCESSES (by CPU):
""")
    procs = []
    for p in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(p.info)
        except:
            pass
    procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
    for i, p in enumerate(procs[:5], 1):
        name = (p['name'] or "?")[:25]
        cpu = p.get('cpu_percent', 0)
        mem = p.get('memory_percent', 0)
        print(f"  {i}. {name:<25} CPU:{cpu:>5.1f}% MEM:{mem:>5.1f}%")
    
    print("="*60)
    print("  Press Ctrl+C to quit")
    print("="*60)
    
    time.sleep(2)