import os, time, requests, psutil, json, subprocess
from datetime import datetime
from collections import deque, Counter
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Group
from rich.progress import Progress, BarColumn, TextColumn, ProgressBar
from rich.align import Align
from rich.text import Text
from rich.columns import Columns

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/tags"
call_logs = deque(maxlen=10)
model_counts = Counter()

# Use cases directly from Screenshot 2026-05-14 at 10.47.35 AM_2.png
MODEL_HINTS = {
    "qwen2.5:7b": "Workhorse: Best all-around 7B",
    "llama3.2:3b": "Speed: Fast lane for gateway tasks",
    "qwen2.5-coder:7b": "Coding: Purpose-built for code",
    "phi4-mini": "Reasoning: Punches above weight",
    "qwen2.5:14b": "Quality: Competes with GPT-3.5",
    "gemma3:12b": "Writing: SOTA for nuanced analysis"
}

# Adjusted for "OLLAMA SERVER" and screen width
HEADER_ASCII = """
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗ 
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
"""

def get_gpu_data():
    defaults = {"use": 0, "temp": 0, "power": "0", "vram_pct": 0, "vram_str": "0/8GB"}
    try:
        res = subprocess.run(['rocm-smi', '--showuse', '--showtemp', '--showpower', '--showmemuse', '--json'], 
                             capture_output=True, text=True, timeout=1)
        data = json.loads(res.stdout)
        card = next(iter(data))
        used = float(data[card].get('VRAM Total Used (B)', 0)) / (1024**3)
        total = float(data[card].get('VRAM Total Memory (B)', 8589934592)) / (1024**3)
        return {
            "use": float(data[card].get('GPU use (%)', 0)),
            "temp": float(data[card].get('Temperature (Sensor edge) (C)', 0)),
            "power": str(data[card].get('Average Graphics Package Power (W)', '0')),
            "vram_pct": (used / total) * 100 if total > 0 else 0,
            "vram_str": f"{used:.1f}/{total:.1f}GB"
        }
    except: return defaults

def get_active_nodes():
    try:
        res = subprocess.run("netstat -tn | grep :11434", shell=True, capture_output=True, text=True, timeout=1)
        nodes = {line.split()[4].split(':')[0] for line in res.stdout.strip().split('\n') if len(line.split()) > 4}
        return [ip for ip in nodes if ip not in ["127.0.0.1", "0.0.0.0", ""]]
    except: return []

def update_call_logs():
    try:
        output = subprocess.check_output(["journalctl", "-u", "ollama", "-n", "10", "--no-pager"], text=True, timeout=1)
        for line in output.split('\n'):
            if "[GIN]" in line and "/api/tags" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5:
                    log_entry = {"time": line[:16].strip(), "status": parts[1], "source": parts[3], "call": parts[4]}
                    if log_entry not in call_logs: 
                        call_logs.append(log_entry)
                        # Tally counts for installed models based on API string
                        for m_key in MODEL_HINTS.keys():
                            if m_key in parts[4]:
                                model_counts[m_key] += 1
    except: pass

def create_hero_panel(name, pct, color, detail="", vram_pct=None, vram_str=""):
    safe_pct = float(pct) if pct is not None else 0.0
    p = Progress(BarColumn(bar_width=15), TextColumn("[bold]{task.percentage:>3.0f}%"))
    p.add_task("", completed=safe_pct)
    elems = [Text(f"{safe_pct:.0f}%", style=f"bold {color}", justify="center"), p, Text(str(detail), style="dim", justify="center")]
    if vram_pct is not None:
        elems.append(Text(f"\nVRAM: {vram_str}", style="bold red", justify="center"))
        elems.append(ProgressBar(total=100, completed=float(vram_pct), width=15))
    else:
        elems.append(Text("\n\n"))
    return Panel(Align.center(Group(*elems), vertical="middle"), title=name, border_style=color, height=10)

def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=9),
        Layout(name="hero_stats", size=11),
        Layout(name="middle_row", ratio=2),
        Layout(name="logs", ratio=2),
        Layout(name="footer", size=3)
    )
    layout["middle_row"].split_row(Layout(name="models", ratio=5), Layout(name="analytics", ratio=4))
    return layout

layout = make_layout()
try:
    with Live(layout, refresh_per_second=2, screen=True) as live:
        while True:
            gpu = get_gpu_data()
            mem = psutil.virtual_memory()
            update_call_logs()
            
            layout["header"].update(Panel(Align.center(Text(HEADER_ASCII, style="bold blue"), vertical="middle"), border_style="blue"))

            layout["hero_stats"].update(Columns([
                create_hero_panel("CPU", psutil.cpu_percent(), "cyan", "SYSTEM LOAD"),
                create_hero_panel("MEM", mem.percent, "magenta", f"{mem.used//10**9}G / {mem.total//10**9}G TOTAL"),
                create_hero_panel("RX 570", gpu["use"], "red", f"{gpu['temp']}°C | {gpu['power']}W", vram_pct=gpu["vram_pct"], vram_str=gpu["vram_str"])
            ], expand=True))

            try:
                r = requests.get(OLLAMA_URL, timeout=1)
                m_data = r.json().get('models', [])
                m_t = Table(expand=True, box=None)
                m_t.add_column("Model", style="cyan", width=18)
                m_t.add_column("Purpose / Use Case", style="dim")
                m_t.add_column("Calls", justify="right", style="yellow")
                m_t.add_column("Size", justify="right", style="magenta")
                for m in m_data[:6]:
                    m_full_name = m['name']
                    m_base = m_full_name.split(':')[0]
                    hint = MODEL_HINTS.get(m_full_name, MODEL_HINTS.get(m_base, "General Inference"))
                    count = model_counts[m_full_name] or model_counts[m_base]
                    m_t.add_row(m_full_name, hint, str(count), f"{m['size']/(1024**3):.1f}GB")
                layout["models"].update(Panel(m_t, title="INSTALLED MODELS", border_style="blue"))
            except: pass

            nodes = get_active_nodes()
            node_display = "\n".join([f"• {n}" for n in nodes]) if nodes else "Listening..."
            ana_grid = Table.grid(expand=True)
            ana_grid.add_column(ratio=1); ana_grid.add_column(ratio=1)
            ana_grid.add_row(
                Group(Text("TRAFFIC STATS", style="bold yellow"), Text(f"Session: {sum(model_counts.values())}", style="dim"), Text(f"Nodes: {len(nodes)}", style="dim")),
                Group(Text("ACTIVE NODES", style="bold cyan"), Text(node_display, style="green"))
            )
            layout["analytics"].update(Panel(ana_grid, title="NODE ANALYTICS", border_style="white", padding=(1, 2)))

            l_t = Table(expand=True, box=None, row_styles=["", "dim"])
            l_t.add_column("Time", width=10); l_t.add_column("Stat", width=6); l_t.add_column("Origin", style="cyan"); l_t.add_column("API Call")
            for log in reversed(list(call_logs)):
                l_t.add_row(str(log.get("time")), str(log.get("status")), str(log.get("source")), str(log.get("call")))
            layout["logs"].update(Panel(l_t, title="LIVE API TRAFFIC", border_style="magenta"))
            
            uptime = str(datetime.now() - datetime.fromtimestamp(psutil.boot_time())).split('.')[0]
            layout["footer"].update(Align.center(Text(f"IP: 10.1.10.89 | STATUS: ONLINE | UPTIME: {uptime}", style="dim")))
            time.sleep(0.5)
except KeyboardInterrupt:
    pass