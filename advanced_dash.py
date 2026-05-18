import os, time, requests, psutil, json, subprocess, re, hashlib
from datetime import datetime
from collections import deque, Counter
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Group
from rich.align import Align
from rich.text import Text
from rich.columns import Columns

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/tags"
call_logs = deque(maxlen=10)
model_counts = Counter()
processed_log_hashes = set()
recent_calls_cache = {}  # Tracks model_name -> timestamp to prevent double-counting multi-line entries

MODEL_HINTS = {
    "qwen2.5:7b": "Workhorse: Best all-around 7B",
    "llama3.2:3b": "Speed: Fast lane for gateway tasks",
    "qwen2.5-coder:7b": "Coding: Purpose-built for code",
    "phi4-mini": "Reasoning: Punches above weight",
    "qwen2.5:14b": "Quality: Competes with GPT-3.5",
    "gemma3:12b": "Writing: SOTA for nuanced analysis"
}

HEADER_ASCII = """
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗ 
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
"""

def get_speedometer(percent, color, title, details):
    """Creates a speedometer-style ASCII gauge displaying descriptive totals."""
    percent = max(0, min(100, percent))
    num_segments = 15
    filled = int((percent / 100) * num_segments)
    gauge_bg = "·" * (num_segments - filled)
    gauge_fill = "█" * filled
    
    arc = Text()
    arc.append("  ╭", style=color)
    arc.append("─" * num_segments, style="dim")
    arc.append("╮  \n", style=color)
    
    arc.append(" [ ", style="white")
    arc.append(gauge_fill, style=color)
    arc.append(gauge_bg, style="dim")
    arc.append(" ] ", style="white")
    
    return Align.center(
        Group(
            arc,
            Text(f"\n{title}: {percent:>3.0f}%", style=f"bold {color}"),
            Text(details, style="dim italic")
        ), vertical="middle"
    )

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
            "vram_str": f"{used:.1f} GB / {total:.1f} GB"
        }
    except: return defaults

def get_active_nodes():
    try:
        res = subprocess.run("ss -tnp | grep :11434", shell=True, capture_output=True, text=True, timeout=1)
        nodes = set()
        for line in res.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5:
                remote = parts[4].rsplit(':', 1)[0].replace('[', '').replace(']', '').replace("::ffff:", "")
                if remote not in ["0.0.0.0", "*", "127.0.0.1", "::1", ""]: nodes.add(remote)
        return list(nodes)
    except: return []

def update_call_logs():
    try:
        output = subprocess.check_output(["journalctl", "-u", "ollama", "-n", "150", "--no-pager"], text=True, timeout=1)
        
        for line in output.split('\n'):
            if not line.strip() or "/api/tags" in line or "/api/ps" in line: continue
            
            line_hash = hashlib.md5(line.encode()).hexdigest()
            if line_hash in processed_log_hashes: continue
            processed_log_hashes.add(line_hash)
            
            # --- 1. MODEL CALLS TRACKING WITH DEBOUNCING ---
            # Triggers on standard JSON logs or raw service markers for request initiation
            has_event = any(k in line for k in [
                'msg="load request"', 'msg="completion request"', 
                '"msg":"load request"', '"msg":"completion request"',
                'path=/api/chat', 'path=/api/generate',
                '"path":"/api/chat"', '"path":"/api/generate"'
            ])
            
            if has_event:
                model_match = re.search(r'(?:model|model_name)[":=]+\s*["\']?([\w\.\-:]+)', line, re.IGNORECASE)
                if model_match:
                    raw_model = model_match.group(1).strip('"\'')
                    current_time = time.time()
                    
                    # 1.5-second debounce ensures multi-line reporting per request registers as 1 count
                    if current_time - recent_calls_cache.get(raw_model, 0) > 1.5:
                        model_counts[raw_model] += 1
                        recent_calls_cache[raw_model] = current_time

            # --- 2. TRAFFIC LOGS (Live List) ---
            entry = None
            if 'status=200' in line:
                ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                path_m = re.search(r'path=([/\w]+)', line)
                rem_m = re.search(r'remote=([\d\.\w:]+)', line)
                if path_m:
                    entry = {
                        "time": ts_m.group(1) if ts_m else "00:00",
                        "status": "200",
                        "source": rem_m.group(1).replace("::ffff:", "") if rem_m else "local",
                        "call": path_m.group(1)
                    }
            elif "[GIN]" in line and " 200 " in line:
                parts = line.split("|")
                if len(parts) >= 5:
                    ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                    entry = {"time": ts_m.group(1) if ts_m else "00:00", "status": "200", "source": parts[3].strip().replace("::ffff:", ""), "call": parts[4].strip().split()[1]}

            if entry and entry not in call_logs:
                call_logs.append(entry)
            
            if len(processed_log_hashes) > 1500: processed_log_hashes.clear()
    except Exception: pass

def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=9),
        Layout(name="hero_stats", size=10),
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
            gpu, mem = get_gpu_data(), psutil.virtual_memory()
            update_call_logs()
            
            # Header
            layout["header"].update(Panel(Align.center(Text(HEADER_ASCII, style="bold blue"), vertical="middle"), border_style="blue"))
            
            # Detailed Stats Speedometers
            mem_used_gb = mem.used / (1024**3)
            mem_total_gb = mem.total / (1024**3)
            layout["hero_stats"].update(Columns([
                Panel(get_speedometer(psutil.cpu_percent(), "cyan", "CPU", f"Load: {psutil.cpu_percent():.0f}% | {psutil.cpu_count()} Cores"), title="SYSTEM"),
                Panel(get_speedometer(mem.percent, "magenta", "RAM", f"{mem.percent:.0f}% used, {mem_used_gb:.1f} GB / {mem_total_gb:.1f} GB Used"), title="MEMORY"),
                Panel(get_speedometer(gpu["use"], "red", "GPU", f"{gpu['temp']}°C | {gpu['vram_str']} Used"), title="RX 570 GPU")
            ], expand=True))

            # Models Table with Tag-Agnostic Aggregate Matching
            try:
                r = requests.get(OLLAMA_URL, timeout=1)
                m_data = r.json().get('models', [])
                m_t = Table(expand=True, box=None)
                m_t.add_column("Model", style="cyan", width=22)
                m_t.add_column("Purpose", style="dim")
                m_t.add_column("Calls", justify="right", style="yellow")
                m_t.add_column("Size", justify="right", style="magenta")
                
                for m in m_data[:6]:
                    full_name = m['name'] 
                    base_name = full_name.split(':')[0]
                    
                    # Accumulate counts where logged models intersect with installed base tags
                    count = 0
                    for logged_model, logged_count in model_counts.items():
                        logged_base = logged_model.split(':')[0]
                        if logged_model == full_name or logged_base == base_name or logged_model == base_name:
                            count += logged_count
                    
                    hint = MODEL_HINTS.get(full_name, MODEL_HINTS.get(base_name, "General Inference"))
                    m_t.add_row(full_name, hint, str(count), f"{m['size']/(1024**3):.1f}GB")
                layout["models"].update(Panel(m_t, title="INSTALLED MODELS", border_style="blue"))
            except: pass

            # Node Details
            nodes = get_active_nodes()
            ana_grid = Table.grid(expand=True)
            ana_grid.add_column(ratio=1); ana_grid.add_column(ratio=1)
            ana_grid.add_row(
                Group(Text("TRAFFIC STATS", style="bold yellow"), Text(f"Session: {sum(model_counts.values())}", style="dim"), Text(f"Nodes: {len(nodes)}", style="dim")),
                Group(Text("ACTIVE NODES", style="bold cyan"), Text("\n".join([f"• {n}" for n in nodes]) if nodes else "Listening...", style="green"))
            )
            layout["analytics"].update(Panel(ana_grid, title="NODE ANALYTICS", border_style="white", padding=(1, 2)))

            # Live API Activity Logs
            l_t = Table(expand=True, box=None, row_styles=["", "dim"])
            l_t.add_column("Time", width=10); l_t.add_column("Stat", width=6); l_t.add_column("Origin", style="cyan"); l_t.add_column("API Call")
            for log in reversed(list(call_logs)):
                l_t.add_row(str(log.get("time")), str(log.get("status")), str(log.get("source")), str(log.get("call")))
            layout["logs"].update(Panel(l_t, title="LIVE API TRAFFIC", border_style="magenta"))
            
            uptime = str(datetime.now() - datetime.fromtimestamp(psutil.boot_time())).split('.')[0]
            layout["footer"].update(Align.center(Text(f"STATUS: ONLINE | UPTIME: {uptime}", style="dim")))
            time.sleep(0.5)
except KeyboardInterrupt: pass