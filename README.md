
```
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗ 
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
```

---

# Ollama Server Dashboard

A real-time terminal dashboard for monitoring a locally running [Ollama](https://ollama.com) LLM server. Built with Python and [Rich](https://github.com/Textualize/rich), it provides live system metrics, active model tracking, call log parsing, and an on-demand hardware diagnostics view — all from a single terminal window.

---

## Features

- **Live system gauges** — CPU, RAM, and GPU utilization with sparkline history
- **Active model tracking** — shows models currently loaded in VRAM with size and context
- **Call log parser** — tails journalctl or Docker logs for inference requests, response times, and token counts
- **Installed model catalog** — lists all pulled models with quantization, size, and capability hints
- **Network node discovery** — detects other Ollama nodes reachable on the local network
- **Hardware Diagnostics view** — full SMBIOS dump via `dmidecode`: motherboard, CPU, RAM topology (all slots, installed vs. max capacity), and storage
- **Two-panel navigation** — press `2` for hardware diagnostics, `1` to return to the main dashboard
- **Background polling** — all slow I/O runs in a daemon thread so the display never freezes
- **Unit toggle** — switch between GB and MB display with `b` / `m`

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.9+ | Runtime |
| `rich` | Terminal UI rendering |
| `psutil` | CPU / RAM metrics |
| `requests` | Ollama API calls |
| `rocm-smi` *(optional)* | AMD GPU metrics |
| `dmidecode` *(optional, root)* | Hardware diagnostics view |

Install Python dependencies:

```bash
pip install rich psutil requests
```

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/Nightmare17726/ollama-server-dashboard.git
cd ollama-server-dashboard

# Make the launcher executable and run
chmod +x start_dash.sh
./start_dash.sh
```

The launcher script (`start_dash.sh`) handles the `sudo` elevation required for full hardware diagnostics and sets up the correct Python environment before launching the dashboard.

> **Without `sudo`:** The main dashboard runs normally. The hardware diagnostics view will show placeholder data instead of real SMBIOS output.

---

## Execution

There are three ways to run the dashboard depending on your setup and how much access you need:

**Via the launcher (recommended)**
```bash
./start_dash.sh
```
Handles `sudo` elevation, Python environment, and working directory automatically.

**Direct — no hardware diagnostics**
```bash
python3 "advanced_dashboard Versions/advanced_dash.py"
```
All main dashboard features work. The Hardware Diagnostics view (`2`) will display synthetic placeholder data because `dmidecode` requires root.

**Direct — full hardware diagnostics**
```bash
sudo python3 "advanced_dashboard Versions/advanced_dash.py"
```
Enables real SMBIOS output in the hardware view: actual motherboard info, all RAM slots with installed/max capacity, CPU details, and storage devices.

**On a remote server (via SSH)**
```bash
ssh user@your-server-ip
cd ollama-server-dashboard
./start_dash.sh
```
The dashboard runs entirely in the terminal — no GUI or browser required. Any SSH session works. For persistent sessions that survive disconnects, wrap with `tmux` or `screen`:
```bash
tmux new -s dash
./start_dash.sh
# Detach: Ctrl+B then D  |  Reattach: tmux attach -t dash
```

---

## Configuration Mapping

All tuneable values live near the top of `advanced_dashboard Versions/advanced_dash.py`:

| Variable | Default | What it controls |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434/api/tags` | Ollama host for installed model listing and API calls. Change the host/port to point at a remote instance. |
| `DISPLAY_UNIT` | `'GB'` | Starting display unit for sizes. Toggled at runtime with `b` / `m`. |
| `call_logs` | `deque(maxlen=10)` | How many inference log entries are kept in the call log panel. Increase `maxlen` to show more history. |
| `MODEL_HINTS` | *(dict)* | Per-model capability labels shown in the installed model catalog. Add entries using the full model name as the key (e.g. `'llama3:8b': 'Your label here'`). |
| `rocm-smi` timeout | `1s` | GPU metric subprocess timeout. Increase if `rocm-smi` is slow to respond on your hardware. |
| `dmidecode` timeout | `5s` | Hardware diagnostics subprocess timeout per dmidecode call. |
| Poll interval | `2s` (background thread sleep) | How often `background_poll_worker()` refreshes API data, GPU metrics, logs, and network nodes. |
| Frame pacing | `0.25s` (select timeout) | How often the main render loop ticks. Lower = smoother, higher = less CPU. |

**Pointing at a remote Ollama instance:**
```python
# advanced_dash.py line 21
OLLAMA_URL = 'http://192.168.1.50:11434/api/tags'
```
Also update the hardcoded `/api/ps` call on the background poll line to match the same host.

---

## SCP — Deploying Files to a Remote Server

Use `scp` to push updated dashboard files to your Ollama server without cloning the full repo each time.

**Copy a single updated file:**
```bash
scp "advanced_dashboard Versions/advanced_dash.py" user@server-ip:~/ollama-server-dashboard/"advanced_dashboard Versions/advanced_dash.py"
```

**Copy the entire repo folder:**
```bash
scp -r ollama-server-dashboard/ user@server-ip:~/
```

**Copy with a non-standard SSH port (e.g. 2222):**
```bash
scp -P 2222 "advanced_dashboard Versions/advanced_dash.py" user@server-ip:~/ollama-server-dashboard/"advanced_dashboard Versions/advanced_dash.py"
```

**Copy using an identity file (SSH key):**
```bash
scp -i ~/.ssh/your_key.pem "advanced_dashboard Versions/advanced_dash.py" user@server-ip:~/ollama-server-dashboard/"advanced_dashboard Versions/advanced_dash.py"
```

**Pull a file back from the server (reverse direction):**
```bash
scp user@server-ip:~/ollama-server-dashboard/"advanced_dashboard Versions/advanced_dash.py" ./local_backup.py
```

> **Note:** Quote paths that contain spaces (`"advanced_dashboard Versions/..."`) on both the local and remote sides. The `-r` flag is required for copying directories recursively.

**SCP syntax quick reference:**
```
scp [options] source destination

source / destination format:
  local path        →  relative/path/to/file  or  /absolute/path
  remote path       →  user@host:/path/on/server

common options:
  -P <port>         non-default SSH port
  -i <keyfile>      SSH identity file
  -r                recursive (copy directories)
  -p                preserve timestamps and permissions
```

---

## Keybinds

| Key | Action |
|---|---|
| `2` | Open Hardware Diagnostics view |
| `1` | Return to Main Dashboard |
| `b` | Display sizes in **GB** |
| `m` | Display sizes in **MB** |
| `Ctrl+C` | Exit |

---

## Repository Structure

```
ollama-server-dashboard/
├── start_dash.sh                    # Launcher script (handles sudo + env)
├── advanced_dashboard Versions/
│   ├── advanced_dash (OG).py        # Original single-screen version
│   └── advanced_dash.py             # Current full-featured version
└── Misc Programs/
    └── ram_check.py                 # Standalone RAM slot diagnostic tool
```

---

## Configuration

The dashboard connects to Ollama at `http://localhost:11434` by default. To point it at a different host, edit `OLLAMA_URL` near the top of `advanced_dash.py`.

GPU metrics require `rocm-smi` to be installed and on your `PATH` (AMD GPUs only). If `rocm-smi` is not found, the GPU panel shows zeroed-out values rather than erroring.

---

## Tested On

- Ubuntu 22.04 / 24.04
- AMD Radeon RX series (rocm-smi)
- ASUS Sabertooth X79 + DDR3 / DDR4 configurations

---

## License

MIT
