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

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/tags"
call_logs = deque(maxlen=10)
model_counts = Counter()
processed_log_hashes = set()
processed_traffic_sigs = set()  
active_models_global = []       

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

def get_color_style(percent):
    """Evaluates percentage values against thresholds and maps to appropriate styles."""
    if percent < 50:
        return "bold white"
    elif percent <= 80:
        return "bold yellow"
    else:
        return "bold red"

def get_speedometer(percent, color, details):
    """Creates an ASCII gauge block centered inside its panel row with extra trailing line padding."""
    percent = max(0, min(100, percent))
    num_segments = 15
    filled = int((percent / 100) * num_segments)
    gauge_bg = "·" * (num_segments - filled)
    gauge_fill = "█" * filled
    
    text_style = get_color_style(percent)
    
    content = Text()
    content.append(f"╭{'─' * num_segments}╮\n", style=color)
    content.append("[ ", style="white")
    content.append(gauge_fill, style=color)
    content.append(gauge_bg, style="dim")
    content.append(" ]\n", style="white")
    content.append(details, style=text_style)
    content.append("\n ") # Injects space under the details line inside the block
    
    return Align.center(content, vertical="middle")

def get_gpu_data():
    defaults = {"use": 0, "temp": 0, "power": "0", "vram_pct": 0, "vram_str": "0.0 GB / 8.0 GB"}
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

def get_disk_info():
    drives = []
    try:
        for part in psutil.disk_partitions(all=False):
            if os.name != 'nt':
                if part.fstype in ['tmpfs', 'devtmpfs', 'devfs', 'proc', 'sysfs', 'overlay', 'squashfs']: 
                    continue
                if any(x in part.mountpoint for x in ['/var/lib/docker', '/snap', '/boot']):
                    continue
            else:
                if 'cdrom' in part.opts or part.fstype == '': 
                    continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.total == 0: continue
                drives.append({
                    "mount": part.mountpoint,
                    "used": usage.used / (1024**3),
                    "total": usage.total / (1024**3),
                    "free": usage.free / (1024**3),
                    "percent": usage.percent
                })
            except: continue
    except: pass
    return drives

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

def update_call_logs(active_models):
    try:
        output = ""
        for cmd in [["journalctl", "-u", "ollama", "-n", "100", "--no-pager"], ["journalctl", "--user", "-u", "ollama", "-n", "100", "--no-pager"]]:
            try:
                output = subprocess.check_output(cmd, text=True, timeout=1)
                if output.strip(): break
            except: continue
        
        if not output.strip():
            try: output = subprocess.check_output(["docker", "logs", "--tail", "100", "ollama"], text=True, timeout=1)
            except: pass

        for line in output.split('\n'):
            if not line.strip() or "/api/tags" in line or "/api/ps" in line: continue
            
            line_hash = hashlib.md5(line.encode()).hexdigest()
            if line_hash in processed_log_hashes: continue
            processed_log_hashes.add(line_hash)
            
            entry = None
            is_successful_call = False
            
            if 'status=200' in line:
                ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                path_m = re.search(r'path=([/\w]+)', line)
                rem_m = re.search(r'remote=([\d\.\w:]+)', line)
                if path_m and any(x in path_m.group(1) for x in ["/api/chat", "/api/generate"]):
                    is_successful_call = True
                    entry = {
                        "time": ts_m.group(1) if ts_m else "00:00",
                        "status": "200",
                        "source": rem_m.group(1).replace("::ffff:", "") if rem_m else "local",
                        "call": path_m.group(1)
                    }
            elif "[GIN]" in line and " 200 " in line and any(x in line for x in ["/api/chat", "/api/generate"]):
                parts = line.split("|")
                if len(parts) >= 5:
                    is_successful_call = True
                    ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                    entry = {
                        "time": ts_m.group(1) if ts_m else "00:00", 
                        "status": "200", 
                        "source": parts[3].strip().replace("::ffff:", ""), 
                        "call": parts[4].strip().split()[1]
                    }

            if entry and entry not in call_logs:
                call_logs.append(entry)

            if is_successful_call and entry:
                sig = f"{entry['time']}_{entry['source']}_{entry['call']}"
                if sig not in processed_traffic_sigs:
                    processed_traffic_sigs.add(sig)
                    
                    model_match = re.search(r'(?:model|model_name)[":=]+\s*["\']?([\w\.\-:]+)', line, re.IGNORECASE)
                    attributed = False
                    if model_match:
                        raw_model = model_match.group(1).strip('"\'')
                        model_counts[raw_model] += 1
                        attributed = True
                    else:
                        for target_key in MODEL_HINTS.keys():
                            if target_key.split(':')[0] in line or target_key in line:
                                model_counts[target_key] += 1
                                attributed = True
                                break
                    
                    if not attributed and active_models:
                        for am in active_models:
                            model_counts[am] += 1
                            break
                            
        if len(processed_log_hashes) > 2000: processed_log_hashes.clear()
        if len(processed_traffic_sigs) > 1000: processed_traffic_sigs.clear()
    except Exception: pass

def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=9),
        Layout(name="hero_stats", size=6), # Height scaled to exactly 6 to safely capture the space injection
        Layout(name="middle_row", ratio=2),
        Layout(name="logs", ratio=2),
        Layout(name="footer", size=3)
    )
    layout["hero_stats"].split_row(
        Layout(name="cpu", ratio=1),
        Layout(name="ram", ratio=1),
        Layout(name="gpu", ratio=1)
    )
    layout["middle_row"].split_row(Layout(name="models", ratio=5), Layout(name="analytics", ratio=4))
    return layout

layout = make_layout()
try:
    with Live(layout, refresh_per_second=2, screen=True) as live:
        while True:
            try:
                ps_r = requests.get("http://localhost:11434/api/ps", timeout=0.5)
                active_models_global = [m['name'] for m in ps_r.json().get('models', [])] if ps_r.status_code == 200 else []
            except: active_models_global = []

            gpu, mem = get_gpu_data(), psutil.virtual_memory()
            update_call_logs(active_models_global)
            
            # Header
            layout["header"].update(Panel(Align.center(Text(HEADER_ASCII, style="bold blue"), vertical="middle"), border_style="blue"))
            
            # Hardware Status Grid
            cpu_pct = psutil.cpu_percent()
            mem_used_gb, mem_total_gb = mem.used / (1024**3), mem.total / (1024**3)
            
            layout["cpu"].update(Panel(get_speedometer(cpu_pct, "cyan", f"CPU {cpu_pct:.0f}% | {psutil.cpu_count()} Cores"), title="SYSTEM", border_style="cyan"))
            layout["ram"].update(Panel(get_speedometer(mem.percent, "magenta", f"RAM {mem.percent:.0f}% | {mem_used_gb:.1f}/{mem_total_gb:.1f} GB"), title="MEMORY", border_style="magenta"))
            layout["gpu"].update(Panel(get_speedometer(gpu["use"], "red", f"GPU {gpu['use']:.0f}% | {gpu['vram_str']}"), title="RX 570 GPU", border_style="red"))

            # Models & Storage Info
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
                    
                    count = 0
                    for logged_model, logged_count in model_counts.items():
                        if logged_model == full_name or logged_model.split(':')[0] == base_name or logged_model == base_name:
                            count += logged_count
                    
                    hint = MODEL_HINTS.get(full_name, MODEL_HINTS.get(base_name, "General Inference"))
                    m_t.add_row(full_name, hint, str(count), f"{m['size']/(1024**3):.1f}GB")

                d_t = Table(expand=True, box=None)
                d_t.add_column("Drive/Mount", style="green", width=18)
                d_t.add_column("Used / Total", justify="right", style="cyan")
                d_t.add_column("Available Space", justify="right", style="yellow")
                d_t.add_column("Usage Bar", justify="right")
                
                for d in get_disk_info()[:4]:
                    bar_w = 10
                    fill_seg = int((d["percent"] / 100) * bar_w)
                    ascii_bar = f"[{'█' * fill_seg}{'·' * (bar_w - fill_seg)}]"
                    
                    # Apply standardized dynamic color rule for disk arrays
                    disk_color = get_color_style(d["percent"]).replace("bold ", "")
                    
                    d_t.add_row(
                        d["mount"],
                        f"{d['used']:.1f}/{d['total']:.1f} GB",
                        f"{d['free']:.1f} GB",
                        Text(f"{ascii_bar} {d['percent']:.0f}%", style=disk_color)
                    )

                env_group = Group(
                    m_t,
                    Text("\n" + "─" * 65, style="dim text"),
                    Text("SYSTEM STORAGE DRIVES", style="bold green"),
                    d_t
                )
                layout["models"].update(Panel(env_group, title="INSTALLED MODELS & STORAGE", border_style="blue"))
            except Exception: pass

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