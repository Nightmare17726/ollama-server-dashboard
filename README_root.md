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
