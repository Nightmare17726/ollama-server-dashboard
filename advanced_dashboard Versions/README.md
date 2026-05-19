
```
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗ 
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
```

---

# Advanced Dashboard Versions

This folder contains the full development history of the Ollama server dashboard — from the original proof-of-concept to the current production version.

---

## Files

| File | Size | Description |
|---|---|---|
| `advanced_dash (OG).py` | ~9 KB | Original single-screen version |
| `advanced_dash.py` | ~33 KB | Current full-featured version |

---

## `advanced_dash (OG).py` — Original Version

The first working dashboard. Single-screen layout using `rich.progress.BarColumn` for animated progress indicators. Demonstrates the core concept: polling the Ollama API and rendering live metrics in the terminal.

**What it has:**
- Live CPU, RAM display via `psutil`
- Ollama active model listing via `/api/ps`
- Installed model catalog via `/api/tags`
- Basic call log parsing
- Animated Rich progress bars

**What it lacks:**
- No keyboard input or multi-screen navigation
- No hardware diagnostics view
- All I/O runs synchronously in the main loop (can cause display stutter)
- No GPU metrics
- No background polling thread

Good reference for understanding the foundational structure before the complexity of the full version was added.

---

## `advanced_dash.py` — Current Version

The production dashboard. A complete rewrite with a two-panel state machine, background I/O threading, raw terminal keyboard input, and a full hardware diagnostics view.

**Architecture highlights:**

- **Two independent layouts** — `make_main_layout()` and `make_hw_layout()` are complete standalone `rich.Layout` trees. Switching views calls `live.update(cur)` with the alternate layout object. This avoids a critical Rich bug where embedding a Layout inside another Layout via `.update()` breaks height calculation and silently kills the refresh thread.

- **Background polling thread** — `background_poll_worker()` runs as a daemon thread, calling the Ollama API, parsing logs, querying GPU metrics, and probing network nodes every 2 seconds. Results are stored in `_poll_cache`. The main render loop reads from the cache and never blocks.

- **Raw keyboard input** — `tty.setcbreak()` puts stdin in cbreak mode before the `Live` context starts. The main loop uses `select.select()` with a 0.25s timeout as the frame pacer, then `os.read()` to consume individual bytes without buffering. No background thread required for keyboard handling.

- **Hardware diagnostics** — on pressing `2`, a background thread runs `collect_hardware_data_bg()`, which calls `dmidecode -t 2/16/17` with 5-second timeouts. Results populate `hw_cache`. The view renders a progress bar while collection runs, then switches to full slot-level RAM topology, CPU info, and storage once ready.

**Features:**
- Live CPU / RAM / GPU gauges with sparkline history
- Active model tracking (VRAM usage, context window, load time)
- Inference call log with response time and token count
- Installed model catalog with quantization hints
- Network node discovery via `ss`
- Full RAM topology — all slots, installed vs. max capacity per slot, physical L→R order
- Motherboard and storage info via dmidecode
- `2` / `1` keyboard navigation between views
- `b` / `m` to toggle GB / MB display
- AMD GPU support via `rocm-smi`

---

## Why Two Files?

The OG version is kept as a reference. If you want a minimal starting point to adapt for a different use case — a different local API, a simpler metric set — the OG version is far easier to modify. The current version prioritizes completeness and robustness over simplicity.

---

## Running the Current Version

From the repo root:

```bash
./start_dash.sh
```

Or directly (hardware diagnostics will show placeholder data without sudo):

```bash
python3 "advanced_dashboard Versions/advanced_dash.py"
```

For full hardware diagnostics:

```bash
sudo python3 "advanced_dashboard Versions/advanced_dash.py"
```

See the [root README](../README.md) for full setup instructions and keybind reference.
