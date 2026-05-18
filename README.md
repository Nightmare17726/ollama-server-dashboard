# 📊 Ollama Advanced Server Dashboard

A professional, high-performance Terminal User Interface (TUI) for monitoring local Ollama instances, model execution logs, active cluster connections, and underlying hardware infrastructure. Designed explicitly for lean server deployments needing instantaneous, dense metrics without heavy web stacks.

```
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗ 
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
```

---

## ✨ Features

* **⏱️ Speedometer ASCII Gauges:** Proportional 1:1:1 grid-locked visual columns representing real-time CPU load, Memory footprint, and **AMD GPU (ROCM-SMI)** core performance. Displays explicit absolute resource metrics (`used / total`).
* **🎨 Dynamic Traffic Color Coding:** Real-time color mapping system applied across server load readouts and data tables (< 50% → White, 50-80% → Yellow, > 80% → Red) to pinpoint resource stress instantly.
* **🧠 Hybrid VRAM Memory Attribution:** Advanced log tracking cross-references real-time active VRAM via Ollama's active scheduling APIs, allowing reliable request counting even when standard router loggers scrub model tags from strings.
* **🌐 Automated Clean Node Analytics:** Discovers incoming node traffic while stripping internal loopback flags (`127.0.0.1`, `::1`) and filtering out messy IPv6 dual-stack encapsulation syntax (`::ffff:`).
* **🗄️ OS File System Map:** Live partition scanning loops through all physical system volumes and charts mount locations alongside visual percentage consumption indicators.
* **⚡ Zero-Padding Dense Engine:** Tight screen layout alignment ensures that panels mesh into flush rows without terminal line-wasting spacing leaks.

---

## 🛠️ Prerequisites & System Requirements

The dashboard depends directly on accessing native system logs (`journalctl`) and system state flags. 

1. **Python Dependencies:**
   ```bash
   pip install rich psutil requests
   ```

2. **System Log Access Configuration (CRITICAL):**
   Standard users do not have permissions to query systemd services. Grant permissions to read internal Ollama logs securely without needing `sudo`:
   ```bash
   sudo usermod -aG systemd-journal $USER
   ```
   *Note: You must log out and log back into your terminal session for this change to take effect.*

3. **Hardware Engine Support:**
   Designed to ingest JSON telemetry from `rocm-smi` tools for modern AMD platforms. Fallbacks ensure standard CPU/RAM tracking components operate continuously if GPU nodes are uninitialized.

---

## 🚀 Execution

Run the script from any terminal environment supporting true-color ANSI processing:

```bash
python3 advanced_dash.py
```

To stop the dashboard monitoring loop at any time, press `Ctrl + C`.

---

## 🔧 Configuration Mapping

Modify the upper `MODEL_HINTS` dictionary inside `advanced_dash.py` to match your local inventory tags and specify semantic labels for the model rendering loop:

```python
MODEL_HINTS = {
    "qwen2.5:7b": "Workhorse: Best all-around 7B",
    "llama3.2:3b": "Speed: Fast lane for gateway tasks",
    "qwen2.5-coder:7b": "Coding: Purpose-built for code",
    "phi4-mini": "Reasoning: Punches above weight"
}
```

---

## 🚀 Secure Copy (scp) Syntax Guide

To push the code or documentation cleanly over your local network between your machines, use the appropriate syntax layout below:

```bash
# Push files to your remote server node
scp advanced_dash.py README.md username@remote_host_ip:/home/username/

# Push to a remote server utilizing a custom SSH configuration port (e.g., 2222)
scp -P 2222 advanced_dash.py README.md username@remote_host_ip:/home/username/

# Pull target assets down from a remote architecture footprint to your current directory
scp username@remote_host_ip:/home/username/advanced_dash.py ./
```

---

## 📝 License

Distributed under the MIT License. See `LICENSE` for details.
