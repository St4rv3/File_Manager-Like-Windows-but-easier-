# STABLE TASK MANAGER v5.0

A console-based system monitor and process manager with a color interface. Supports two modes: full UI (prompt_toolkit) and terminal mode.

![Demo](demo.gif)

## 📦 Features

### System Monitoring
- 📊 **Real-time metrics** — CPU, RAM, disk, network
- 📈 **CPU history chart** — visual ASCII graph
- 💾 **Memory details** — used/available in GB
- ⏱ **Uptime** — system running time
- 🔢 **CPU info** — number of cores

### Process Management
- 🔍 **Search** — filter processes by name
- 🎯 **Sort** — by CPU, memory, name, PID
- ⬆️⬇️ **Scroll** — page through all processes
- ❌ **Kill** — terminate processes by PID

### Data & Export
- 💾 **Logging** — metrics to SQLite
- 📤 **CSV export** — export logs
- 🧹 **Cleanup** — delete old records
- ⚙️ **Config** — settings in config.json

## 📁 Files

| File | Description |
|------|-------------|
| `main.py` | Main version (full UI, requires Windows Terminal) |
| `main_terminal.py` | Terminal version with hotkeys |
| `main_input.py` | Input-based version (compatible) |

## 🖥️ Requirements

- Python 3.8+
- psutil
- prompt_toolkit (for main.py)

## ⚡️ Installation

```bash
pip install psutil prompt_toolkit
```

## 🚀 Usage

### Option 1: main_input.py (recommended for VS Code)
```bash
python main_input.py
```

Commands:
- `/text` — search (e.g., `/python`)
- `k PID` — kill (e.g., `k 15372`)
- `number` — kill by PID
- `w` — page up
- `s` — page down
- `r` — reset filter
- `q` — quit

### Option 2: main_terminal.py (for Windows Terminal / cmd)
```bash
python main_terminal.py
```

Hotkeys:
- `/` — search mode
- `k` — kill mode
- `w/s` — scroll
- `r` — reset
- `q` — quit
- `ESC` — cancel

### Option 3: main.py (full UI)
```bash
python main.py
```
Requires Windows Terminal or cmd.exe with full-screen support.

## ⌨️ Controls (main.py)

| Key | Action |
|-----|--------|
| `←`/`→` | Switch pages |
| `/` | Filter by name |
| `N` | Filter by PID |
| `r` | Reset filter |
| `s` | Change sort |
| `Space` | Sort direction |
| `k` | Kill process |
| `K` | Kill process tree |
| `F1` | Help |
| `q` | Quit |

## 📊 Pages

### PROCESSES
Process list with PID, name, CPU%, MEM%, DISK I/O

### SYSTEM
- CPU, RAM, DISK progress bars
- CPU history graph
- Uptime, CPU cores
- Network (↑/↓)

### NETWORK
- TCP/UDP connections
- Port filter

### LOGS
Metrics history from DB

### HELP
Help page

## 🗄️ Database

Auto-creates `metrics.db`:

| Field | Type |
|-------|------|
| id | INTEGER |
| timestamp | TEXT |
| cpu | REAL |
| memory | REAL |
| disk_percent | REAL |
| net_sent | INTEGER |
| net_recv | INTEGER |

## ⚙️ Configuration

Creates `config.json`:

```json
{
  "refresh_interval": 1,
  "max_procs": 100,
  "history_size": 60,
  "log_retention_days": 7
}
```

## 📝 License

MIT License