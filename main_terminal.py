#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Terminal version with search and kill support"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import time
import psutil
import signal
import os
import threading

if os.name == 'nt':
    import msvcrt

def handler(sig, frame):
    print("\n\nDone.")
    sys.exit(0)

signal.signal(signal.SIGINT, handler)

scroll_offset = 0
lines_per_page = 12
input_buffer = ""
input_mode = "view"  # view, search, kill
filter_text = ""

print("STABLE TASK MANAGER v5.0 - Starting...")

def input_listener():
    global scroll_offset, input_buffer, input_mode, filter_text
    if os.name != 'nt':
        return
    try:
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                
                if input_mode == "view":
                    if key == 'w' or key == 'W':
                        scroll_offset = max(0, scroll_offset - 1)
                    elif key == 's' or key == 'S':
                        scroll_offset += 1
                    elif key == 'r' or key == 'R':
                        scroll_offset = 0
                        filter_text = ""
                    elif key == '/':
                        input_mode = "search"
                        input_buffer = ""
                    elif key == 'k' or key == 'K':
                        input_mode = "kill"
                        input_buffer = ""
                    elif key == 'q' or key == 'Q':
                        print("\n\nQuitting...")
                        sys.exit(0)
                
                elif input_mode == "search":
                    if key == '\r':  # Enter
                        filter_text = input_buffer
                        input_mode = "view"
                        scroll_offset = 0
                    elif key == '\x1b':  # ESC
                        input_mode = "view"
                        input_buffer = ""
                    elif key == '\b':  # Backspace
                        input_buffer = input_buffer[:-1]
                    else:
                        input_buffer += key
                
                elif input_mode == "kill":
                    if key == '\r':  # Enter
                        try:
                            pid = int(input_buffer)
                            p = psutil.Process(pid)
                            name = p.name()
                            p.terminate()
                            print(f"\n  [OK] Killed PID {pid} ({name})")
                        except ValueError:
                            print(f"\n  [ERROR] Invalid PID")
                        except psutil.NoSuchProcess:
                            print(f"\n  [ERROR] Process not found")
                        except psutil.AccessDenied:
                            print(f"\n  [ERROR] Access denied (need admin)")
                        except Exception as e:
                            print(f"\n  [ERROR] {e}")
                        input_mode = "view"
                        input_buffer = ""
                        time.sleep(1)
                    elif key == '\x1b':  # ESC
                        input_mode = "view"
                        input_buffer = ""
                    elif key == '\b':  # Backspace
                        input_buffer = input_buffer[:-1]
                    else:
                        input_buffer += key
                        
            time.sleep(0.03)
    except Exception:
        pass

t = threading.Thread(target=input_listener, daemon=True)
t.start()

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
    
    if input_mode == "search":
        print(f"  / Search: {input_buffer}_")
    elif input_mode == "kill":
        print(f"  K PID: {input_buffer}_")
    elif filter_text:
        print(f"  Filter: {filter_text}")
    
    print("-" * 55)
    
    for i, p in enumerate(visible, start + 1):
        name = (p['name'] or '?')[:22]
        pid = p['pid']
        cpu_val = p['cpu_percent']
        mem_val = p['memory_percent']
        print(f" {i:>3}. {name:<22} PID:{pid:<6} CPU:{cpu_val:5.1f}% MEM:{mem_val:5.1f}%")
    
    print("=" * 55)
    print(f" Showing {start+1}-{min(end, total)} of {total} processes")
    
    if input_mode == "view":
        print(f" /:search  k:kill  w/s:scroll  r:reset  q:quit")
    elif input_mode == "search":
        print(f" Type to search, Enter=ok, ESC=cancel")
    elif input_mode == "kill":
        print(f" Type PID, Enter=kill, ESC=cancel")
    
    time.sleep(0.8)