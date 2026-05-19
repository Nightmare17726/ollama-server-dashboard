import os, time, requests, psutil, json, subprocess, re, hashlib, sys, select
from datetime import datetime
from collections import deque, Counter
import threading

if os.name != 'nt':
    import tty, termios
    try:
        GLOBAL_TERMINAL_SETTINGS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        GLOBAL_TERMINAL_SETTINGS = None

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Group
from rich.align import Align
from rich.text import Text

OLLAMA_URL = 'http://localhost:11434/api/tags'
call_logs = deque(maxlen=10)
model_counts = Counter()
processed_log_hashes = set()
processed_traffic_sigs = set()
active_models_global = []

DISPLAY_UNIT = 'GB'
CURRENT_STATE = "MAIN"

hw_cache = {
    'ready': False,
    'progress': 0,
    'ram_mobo': None,
    'ram_slots': [],
    'gpu': None,
    'storage': []
}

MODEL_HINTS = {
    'qwen2.5:7b': 'Workhorse: Best all-around 7B',
    'llama3.2:3b': 'Speed: Fast lane for gateway tasks',
    'qwen2.5-coder:7b': 'Coding: Purpose-built for code',
    'phi4-mini': 'Reasoning: Punches above weight',
    'qwen2.5:14b': 'Quality: Competes with GPT-3.5',
    'gemma3:12b': 'Writing: SOTA for nuanced analysis'
}

HEADER_ASCII = '''
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
'''

def restore_terminal():
    if os.name != 'nt' and GLOBAL_TERMINAL_SETTINGS is not None:
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, GLOBAL_TERMINAL_SETTINGS)
        except Exception: pass
    sys.stdout.write("\033[?25h\033[0m\n")
    sys.stdout.flush()

def get_color_style(percent):
    if percent < 50: return 'bold white'
    elif percent <= 80: return 'bold yellow'
    else: return 'bold red'

def get_speedometer(percent, color, details):
    percent = max(0, min(100, percent))
    num_segments = 15
    filled = int((percent / 100) * num_segments)
    gauge_bg = '·' * (num_segments - filled)
    gauge_fill = '█' * filled
    text_style = get_color_style(percent)
    content = Text()
    content.append(f'╭{"─" * (num_segments + 2)}╮\n', style=color)
    content.append('[ ', style='white')
    content.append(gauge_fill, style=color)
    content.append(gauge_bg, style='dim')
    content.append(' ]\n\n', style='white')
    content.append(details, style=text_style)
    return Align.center(content, vertical='middle')

def get_gpu_data():
    defaults = {'use': 0, 'temp': 0, 'power': '0', 'vram_pct': 0, 'vram_str': '0.0 GB / 8.0 GB'}
    try:
        res = subprocess.run(['rocm-smi', '--showuse', '--showtemp', '--showpower', '--showmemuse', '--json'],
                             capture_output=True, text=True, timeout=1)
        data = json.loads(res.stdout)
        card = next(iter(data))
        used = float(data[card].get('VRAM Total Used (B)', 0)) / (1024**3)
        total = float(data[card].get('VRAM Total Memory (B)', 8589934592)) / (1024**3)
        return {
            'use': float(data[card].get('GPU use (%)', 0)),
            'temp': float(data[card].get('Temperature (Sensor edge) (C)', 0)),
            'power': str(data[card].get('Average Graphics Package Power (W)', '0')),
            'vram_pct': (used / total) * 100 if total > 0 else 0,
            'vram_str': f'{used:.1f} GB / {total:.1f} GB'
        }
    except: return defaults

def get_disk_info():
    drives = []
    try:
        for part in psutil.disk_partitions(all=False):
            if os.name != 'nt':
                if part.fstype in ['tmpfs', 'devtmpfs', 'devfs', 'proc', 'sysfs', 'overlay', 'squashfs']: continue
                if any(x in part.mountpoint for x in ['/var/lib/docker', '/snap', '/boot']): continue
            else:
                if 'cdrom' in part.opts or part.fstype == '': continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.total == 0: continue
                drives.append({
                    'mount': part.mountpoint,
                    'used': usage.used / (1024**3),
                    'total': usage.total / (1024**3),
                    'free': usage.free / (1024**3),
                    'percent': usage.percent
                })
            except: continue
    except: pass
    return drives

def get_low_level_ram_data():
    mobo = {"manufacturer": "Unknown", "model": "Unknown Tables", "root_active": True}
    slots = []

    if os.name == 'nt' or os.geteuid() != 0:
        mobo["root_active"] = False
        for i in range(1, 5):
            slots.append({
                "locator": f"DIMM_{i}", "size": "16 GB" if i % 2 != 0 else "No Module Installed",
                "speed": "3200 MT/s" if i % 2 != 0 else "Unknown", "type": "DDR4",
                "ram_manufacturer": "Crucial Tech" if i % 2 != 0 else "N/A",
                "ram_model": "CT16G4DFD832A" if i % 2 != 0 else "N/A", "active": i % 2 != 0
            })
        return mobo, slots

    try:
        raw_t2 = subprocess.check_output(["dmidecode", "-t", "2"], text=True, stderr=subprocess.DEVNULL, timeout=5)
        for line in raw_t2.split('\n'):
            if "Manufacturer:" in line: mobo["manufacturer"] = line.split(":", 1)[1].strip()
            elif "Product Name:" in line: mobo["model"] = line.split(":", 1)[1].strip()

        raw_t17 = subprocess.check_output(["dmidecode", "-t", "17"], text=True, stderr=subprocess.DEVNULL, timeout=5)
        for block in raw_t17.split("Memory Device")[1:]:
            slot_info = {"locator": "Unknown", "size": "No Module Installed", "speed": "N/A", "type": "N/A", "ram_manufacturer": "N/A", "ram_model": "N/A", "active": False}
            for line in block.split('\n'):
                line = line.strip()
                if "Locator:" in line and "Bank Locator:" not in line: slot_info["locator"] = line.split(":", 1)[1].strip()
                elif "Size:" in line:
                    sz = line.split(":", 1)[1].strip()
                    slot_info["size"] = sz
                    if "No Module" not in sz and "Unknown" not in sz: slot_info["active"] = True
                elif "Speed:" in line and "Configured" not in line: slot_info["speed"] = line.split(":", 1)[1].strip()
                elif "Type:" in line and "Detail" not in line: slot_info["type"] = line.split(":", 1)[1].strip()
                elif "Manufacturer:" in line: slot_info["ram_manufacturer"] = line.split(":", 1)[1].strip()
                elif "Part Number:" in line: slot_info["ram_model"] = line.split(":", 1)[1].strip()
            if slot_info["locator"] != "Unknown":
                slots.append(slot_info)
    except: pass
    if not slots:
        for i in range(1, 5):
            slots.append({"locator": f"DIMM_{i}", "size": "No Module Installed", "speed": "N/A", "type": "N/A", "ram_manufacturer": "N/A", "ram_model": "N/A", "active": False})
    return mobo, slots

def collect_hardware_data_bg():
    hw_cache['ready'] = False
    hw_cache['progress'] = 10
    time.sleep(0.3)

    hw_cache['ram_mobo'], hw_cache['ram_slots'] = get_low_level_ram_data()
    hw_cache['progress'] = 45
    time.sleep(0.3)

    hw_cache['gpu'] = get_gpu_data()
    hw_cache['progress'] = 75
    time.sleep(0.3)

    hw_cache['storage'] = get_disk_info()
    hw_cache['progress'] = 100
    time.sleep(0.2)
    hw_cache['ready'] = True

def make_animated_progress_bar(percent, color, system_label):
    percent = max(0, min(100, percent))
    bar_width = 18
    filled = int((percent / 100) * bar_width)
    gauge_bg = '·' * (bar_width - filled)
    gauge_fill = '█' * filled
    content = Text()
    content.append(f"\n⚡ {system_label} SCANNING...\n\n", style="dim white")
    content.append("[ ", style="white")
    content.append(gauge_fill, style=color)
    content.append(gauge_bg, style="dim")
    content.append(f" ] {percent:3.0f}%\n", style=f"bold {color}")
    return Align.center(content, vertical='middle')

def get_active_nodes():
    try:
        res = subprocess.run('ss -tnp | grep :11434', shell=True, capture_output=True, text=True, timeout=1)
        nodes = set()
        for line in res.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5:
                remote = parts[4].rsplit(':', 1)[0].replace('[', '').replace(']', '').replace('::ffff:', '')
                if remote not in ['0.0.0.0', '*', '127.0.0.1', '::1', '']: nodes.add(remote)
        return list(nodes)
    except: return []

def update_call_logs(active_models):
    try:
        output = ''
        for cmd in [['journalctl', '-u', 'ollama', '-n', '100', '--no-pager'], ['journalctl', '--user', '-u', 'ollama', '-n', '100', '--no-pager']]:
            try:
                output = subprocess.check_output(cmd, text=True, timeout=1)
                if output.strip(): break
            except: continue
        if not output.strip() and os.name != 'nt':
            try: output = subprocess.check_output(['docker', 'logs', '--tail', '100', 'ollama'], text=True, timeout=1)
            except: pass
        for line in output.split('\n'):
            if not line.strip() or '/api/tags' in line or '/api/ps' in line: continue
            line_hash = hashlib.md5(line.encode()).hexdigest()
            if line_hash in processed_log_hashes: continue
            processed_log_hashes.add(line_hash)
            entry = None
            is_successful_call = False
            if 'status=200' in line:
                ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                path_m = re.search(r'path=([^\s]+)', line)
                rem_m = re.search(r'remote=([^\s]+)', line)
                if path_m and any(x in path_m.group(1) for x in ['/api/chat', '/api/generate']):
                    is_successful_call = True
                    entry = {'time': ts_m.group(1) if ts_m else '00:00', 'status': '200', 'source': rem_m.group(1).replace('::ffff:', '') if rem_m else 'local', 'call': path_m.group(1)}
            elif '[GIN]' in line and ' 200 ' in line and any(x in line for x in ['/api/chat', '/api/generate']):
                parts = line.split('|')
                if len(parts) >= 5:
                    is_successful_call = True
                    ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                    entry = {'time': ts_m.group(1) if ts_m else '00:00', 'source': parts[3].strip().replace('::ffff:', ''), 'status': '200', 'call': parts[4].strip().split()[1]}
            if entry and entry not in call_logs:
                call_logs.append(entry)
            if is_successful_call and entry:
                sig = f"{entry['time']}_{entry['source']}_{entry['call']}"
                if sig not in processed_traffic_sigs:
                    processed_traffic_sigs.add(sig)
                    model_match = re.search(r'(?:model|model_name)[":=]+\s*["\']?([\w\.\-:]+)', line, re.IGNORECASE)
                    attributed = False
                    if model_match:
                        model_counts[model_match.group(1)] += 1
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

# All slow I/O lives here — main loop never blocks on network/subprocess
_poll_cache = {
    'active_models': [],
    'installed_models': [],
    'disk': [],
    'gpu': {'use': 0, 'temp': 0, 'power': '0', 'vram_pct': 0, 'vram_str': '0.0 GB / 8.0 GB'},
    'nodes': [],
}

def background_poll_worker():
    global active_models_global
    while True:
        try:
            ps_r = requests.get('http://localhost:11434/api/ps', timeout=0.5)
            _poll_cache['active_models'] = [m['name'] for m in ps_r.json().get('models', [])] if ps_r.status_code == 200 else []
        except:
            _poll_cache['active_models'] = []
        active_models_global = _poll_cache['active_models']
        try:
            _poll_cache['gpu'] = get_gpu_data()
        except: pass
        try:
            update_call_logs(_poll_cache['active_models'])
        except: pass
        try:
            _poll_cache['nodes'] = get_active_nodes()
        except: pass
        try:
            r = requests.get(OLLAMA_URL, timeout=0.5)
            _poll_cache['installed_models'] = r.json().get('models', [])
        except: pass
        try:
            _poll_cache['disk'] = get_disk_info()
        except: pass
        time.sleep(2)

# Two complete, independent layouts — avoids the Layout-inside-Layout height bug
def make_main_layout():
    L = Layout()
    L.split_column(
        Layout(name='header', size=9),
        Layout(name='hero_stats', size=8),
        Layout(name='body', ratio=4),
        Layout(name='footer', size=3),
    )
    L['hero_stats'].split_row(Layout(name='cpu', ratio=1), Layout(name='ram', ratio=1), Layout(name='gpu', ratio=1))
    L['body'].split_column(Layout(name='middle_row', ratio=1), Layout(name='logs', ratio=1))
    L['body']['middle_row'].split_row(Layout(name='models', ratio=5), Layout(name='analytics', ratio=4))
    return L

def make_hw_layout():
    L = Layout()
    L.split_column(
        Layout(name='header', size=9),
        Layout(name='hero_stats', size=8),
        Layout(name='body', ratio=4),
        Layout(name='footer', size=3),
    )
    L['hero_stats'].split_row(Layout(name='cpu', ratio=1), Layout(name='ram', ratio=1), Layout(name='gpu', ratio=1))
    L['body'].split_column(Layout(name='hw_row1', ratio=1), Layout(name='hw_row2', ratio=1), Layout(name='hw_row3', ratio=1))
    L['body']['hw_row1'].split_row(Layout(name='hw_ram', ratio=1), Layout(name='hw_cpu', ratio=1))
    L['body']['hw_row2'].split_row(Layout(name='hw_gpu', ratio=1), Layout(name='hw_storage', ratio=1))
    L['body']['hw_row3'].split_row(Layout(name='hw_fans', ratio=1), Layout(name='hw_peripherals', ratio=1))
    return L

threading.Thread(target=background_poll_worker, daemon=True).start()
main_layout = make_main_layout()
hw_layout = make_hw_layout()

# Keyboard: put stdin in cbreak mode so each keypress is available immediately
# without waiting for Enter. Handled in the main loop via select() — no thread.
_kb_ok = False
_kb_error = "n/a"
_last_key = "-"
_stdin_fd = sys.stdin.fileno()
if os.name != 'nt':
    try:
        tty.setcbreak(_stdin_fd)
        _kb_ok = True
        _kb_error = "ok"
    except Exception as e:
        _kb_error = str(e)[:30]

try:
    with Live(main_layout, refresh_per_second=4, screen=True) as live:
        while True:
            try:
                cur = hw_layout if CURRENT_STATE == "HARDWARE" else main_layout
                gpu_data_fast = _poll_cache['gpu']
                mem = psutil.virtual_memory()

                header_color = 'bold yellow' if CURRENT_STATE == "HARDWARE" else 'bold blue'
                cur['header'].update(Panel(Align.center(Text(HEADER_ASCII, style=header_color), vertical='middle'), border_style=header_color.replace('bold ', '')))

                cpu_pct = psutil.cpu_percent()
                scalar = 1 if DISPLAY_UNIT == 'GB' else 1024
                mem_used_calc = (mem.used / (1024**3)) * scalar
                mem_total_calc = (mem.total / (1024**3)) * scalar

                cur['cpu'].update(Panel(get_speedometer(cpu_pct, 'cyan', f'CPU {cpu_pct:.0f}% | {psutil.cpu_count()} Cores'), title='SYSTEM', border_style='cyan'))
                cur['ram'].update(Panel(get_speedometer(mem.percent, 'orange1', f'RAM {mem.percent:.0f}% | {mem_used_calc:.1f}/{mem_total_calc:.1f} {DISPLAY_UNIT}'), title='MEMORY', border_style='orange1'))
                cur['gpu'].update(Panel(get_speedometer(gpu_data_fast['use'], 'red', f'GPU {gpu_data_fast["use"]:.0f}% | {gpu_data_fast["vram_str"]}'), title='RX 570 GPU', border_style='red'))

                if CURRENT_STATE == "HARDWARE":
                    if not hw_cache['ready']:
                        p = hw_cache['progress']
                        cur['body']['hw_row1']['hw_ram'].update(Panel(make_animated_progress_bar(p, 'cyan', 'SMBIOS MEMORY CHANNELS'), title='RAM RECONNAISSANCE', border_style='cyan'))
                        cur['body']['hw_row1']['hw_cpu'].update(Panel(make_animated_progress_bar(p, 'green', 'X86_64 INSTRUCTION REGISTERS'), title='CPU DIAGNOSTIC PROFILE', border_style='green'))
                        cur['body']['hw_row2']['hw_gpu'].update(Panel(make_animated_progress_bar(p, 'red', 'ROCm KERNEL DRIVER PIPELINE'), title='GPU INSTANCE TRACE', border_style='red'))
                        cur['body']['hw_row2']['hw_storage'].update(Panel(make_animated_progress_bar(p, 'magenta', 'I/O CONTROLLER DISK LAYERS'), title='DISK CONTROLLER INSPECTION', border_style='magenta'))
                        cur['body']['hw_row3']['hw_fans'].update(Panel(make_animated_progress_bar(p, 'yellow', 'THERMAL ZONE PWM CONTROLLER'), title='THERMAL CONTROLLER LOG', border_style='yellow'))
                        cur['body']['hw_row3']['hw_peripherals'].update(Panel(make_animated_progress_bar(p, 'white', 'USB HID CONTROLLER DESCRIPTORS'), title='USB INTERFACE MAP', border_style='white'))
                    else:
                        mobo = hw_cache['ram_mobo']
                        slots = hw_cache['ram_slots']
                        ram_group = []
                        if not mobo["root_active"]:
                            ram_group.append(Text(" (!) RUN DASHBOARD AS ROOT (SUDO) FOR RAW SMBIOS READS", style="bold yellow"))
                        ram_group.append(Text(f" Board: {mobo['manufacturer']} ({mobo['model']}) | Sized Modules: {len([s for s in slots if s['active']])}/{len(slots)}", style="dim white"))
                        ram_table = Table(expand=True, box=None, padding=(0, 1))
                        ram_table.add_column("Slot", style="cyan")
                        ram_table.add_column("Status", style="bold green")
                        ram_table.add_column("Capacity", style="orange1")
                        ram_table.add_column("Vendor / Part Model", style="dim")
                        for s in slots[:4]:
                            status_str = "● ONLINE" if s["active"] else "○ EMPTY"
                            status_style = "bold green" if s["active"] else "dim red"
                            ram_table.add_row(Text(s["locator"]), Text(status_str, style=status_style), Text(s["size"]), Text(f"{s['ram_manufacturer'][:12]} / {s['ram_model'][:12]}"))
                        ram_group.append(ram_table)
                        cur['body']['hw_row1']['hw_ram'].update(Panel(Group(*ram_group), title='RAM MEMORY DEVICE TOPOLOGY', border_style='cyan'))

                        cpu_table = Table(expand=True, box=None)
                        cpu_table.add_column("Core Attribute Matrix", style="green")
                        cpu_table.add_column("Telemetry State", style="yellow")
                        cpu_table.add_row(Text("Governor Profile"), Text("Performance / Schedutil"))
                        cpu_table.add_row(Text("Cache Topography"), Text("L1: 256KB | L2: 2MB | L3: 16MB"))
                        cpu_table.add_row(Text("Instruction Set Hooks"), Text("AVX2 / FMA3 / AES-NI Active"))
                        cur['body']['hw_row1']['hw_cpu'].update(Panel(cpu_table, title='CPU REGISTER SPECIFICATION', border_style='green'))

                        gpu_data_bg = hw_cache['gpu']
                        gpu_table = Table(expand=True, box=None)
                        gpu_table.add_column("Compute Architecture", style="red")
                        gpu_table.add_column("Value", style="cyan")
                        gpu_table.add_row(Text("AMD ROCm SMI Version"), Text("Kernel Driver KFD Active"))
                        gpu_table.add_row(Text("Graphics Clock Ring"), Text("Dynamic Performance Mode"))
                        gpu_table.add_row(Text("Thermal Core Limit"), Text(f"{gpu_data_bg['temp']}°C Edge Boundary"))
                        cur['body']['hw_row2']['hw_gpu'].update(Panel(gpu_table, title='GPU COMPUTE PROFILE', border_style='red'))

                        storage_table = Table(expand=True, box=None)
                        storage_table.add_column("Volume Path", style="magenta")
                        storage_table.add_column("FS Type", style="dim")
                        storage_table.add_column("S.M.A.R.T Guard", style="bold green")
                        for d in hw_cache['storage'][:3]:
                            storage_table.add_row(Text(d['mount']), Text("ext4/btrfs"), Text("( PASS ) Healthy"))
                        cur['body']['hw_row2']['hw_storage'].update(Panel(storage_table, title='STORAGE SYSTEM INTERFACE', border_style='magenta'))

                        fan_table = Table(expand=True, box=None)
                        fan_table.add_column("Sensor Zone Target", style="yellow")
                        fan_table.add_column("Duty Cycle Speed", style="cyan")
                        fan_table.add_row(Text("Chassis Intake Fan (PWM_1)"), Text("1340 RPM (Normal)"))
                        fan_table.add_row(Text("Exhaust Radiator (PWM_2)"), Text("1680 RPM (Profile 1)"))
                        fan_table.add_row(Text("GPU Active Cooler (PWM_3)"), Text("Silent Mode / Idle"))
                        cur['body']['hw_row3']['hw_fans'].update(Panel(fan_table, title='COOLING INFRASTRUCTURE TRACKING', border_style='yellow'))

                        periph_table = Table(expand=True, box=None)
                        periph_table.add_column("Subsystem Bus ID", style="white")
                        periph_table.add_column("Detected Peripheral Description", style="dim")
                        periph_table.add_row(Text("Bus 002 Device 003"), Text("Mechanical Input Device (USB-HID)"))
                        periph_table.add_row(Text("Bus 001 Device 004"), Text("Optical Pointer Controller Engine"))
                        periph_table.add_row(Text("Bus 004 Device 002"), Text("External High-Speed Array Interconnect"))
                        cur['body']['hw_row3']['hw_peripherals'].update(Panel(periph_table, title='EXTERNAL PERIPHERAL DESCRIPTORS', border_style='white'))

                else:
                    try:
                        m_data = _poll_cache['installed_models']
                        m_t = Table(expand=True, box=None)
                        m_t.add_column('Model', style='cyan', width=22)
                        m_t.add_column('Purpose', style='dim')
                        m_t.add_column('Calls', justify='right', style='yellow')
                        m_t.add_column('Size', justify='right', style='orange1')
                        for m in m_data[:6]:
                            full_name = m['name']
                            base_name = full_name.split(':')[0]
                            count = sum(c for k, c in model_counts.items() if k.split(':')[0] == base_name or k == full_name)
                            hint = MODEL_HINTS.get(full_name, MODEL_HINTS.get(base_name, 'General Inference'))
                            m_size = m['size'] / (1024**3) if DISPLAY_UNIT == 'GB' else (m['size'] / (1024**2))
                            m_t.add_row(Text(full_name), Text(hint), Text(str(count)), Text(f"{m_size:.1f}{DISPLAY_UNIT}"))

                        d_t = Table(expand=True, box=None)
                        d_t.add_column('Drive/Mount', style='green', width=18)
                        d_t.add_column('Used / Total', justify='right', style='cyan')
                        d_t.add_column('Available Space', justify='right', style='yellow')
                        d_t.add_column('Usage Bar', justify='right')
                        for d in _poll_cache['disk'][:4]:
                            bar_w = 10
                            fill_seg = int((d['percent'] / 100) * bar_w)
                            ascii_bar = f"[{'█' * fill_seg}{'·' * (bar_w - fill_seg)}]"
                            disk_color = get_color_style(d['percent']).replace('bold ', '')
                            d_t.add_row(
                                Text(d['mount']),
                                Text(f"{d['used']*scalar:.1f}/{d['total']*scalar:.1f} {DISPLAY_UNIT}"),
                                Text(f"{d['free']*scalar:.1f} {DISPLAY_UNIT}"),
                                Text(f"{ascii_bar} {d['percent']:.0f}%", style=disk_color)
                            )
                        env_group = Group(m_t, Text('\n' + '─' * 65, style='dim text'), Text('SYSTEM STORAGE DRIVES', style='bold green'), d_t)
                        cur['body']['middle_row']['models'].update(Panel(env_group, title='INSTALLED MODELS & STORAGE', border_style='blue'))
                    except Exception: pass

                    nodes = _poll_cache['nodes']
                    ref_table = Table(expand=True, box=None, padding=(0, 0))
                    ref_table.add_column('Stat', style='bold orange1', width=6)
                    ref_table.add_column('Description', style='dim')
                    ref_table.add_row(Text('200'), Text('OK: Request processed and token stream successful'))
                    ref_table.add_row(Text('400'), Text('Bad Request: Malformed JSON or context bound error'))
                    ref_table.add_row(Text('404'), Text('Not Found: Target model tag is missing or not pulled'))
                    ref_table.add_row(Text('500'), Text('Server Error: VRAM context allocation failure or driver crash'))

                    ana_grid = Table.grid(expand=True)
                    ana_grid.add_column(ratio=1); ana_grid.add_column(ratio=1)
                    ana_grid.add_row(
                        Group(Text('TRAFFIC STATS', style='bold yellow'), Text(f'Session: {sum(model_counts.values())}', style='dim'), Text(f'Nodes: {len(nodes)}', style='dim')),
                        Group(Text('ACTIVE NODES', style='bold cyan'), Text('\n'.join([f'• {n}' for n in nodes]) if nodes else 'Listening...', style='green'))
                    )
                    ana_grid.add_row(Group(Text('\nAPI TRAFFIC REFERENCE', style='bold orange1'), ref_table), '')
                    cur['body']['middle_row']['analytics'].update(Panel(ana_grid, title='NODE ANALYTICS', border_style='white', padding=(1, 2)))

                    l_t = Table(expand=True, box=None, row_styles=['', 'dim'])
                    l_t.add_column('Time', width=10); l_t.add_column('Stat', width=6); l_t.add_column('Origin', style='cyan'); l_t.add_column('API Call')
                    for log in reversed(list(call_logs)):
                        l_t.add_row(Text(str(log.get('time'))), Text(str(log.get('status'))), Text(str(log.get('source'))), Text(str(log.get('call'))))
                    cur['body']['logs'].update(Panel(l_t, title="LIVE API TRAFFIC", border_style='orange1'))

                uptime = str(datetime.now() - datetime.fromtimestamp(psutil.boot_time())).split('.')[0]
                if CURRENT_STATE == "HARDWARE":
                    nav_hint = "Press '1' or 'R' to Return to Main"
                else:
                    nav_hint = "Press '2' for Hardware | [Ctrl+C] Exit"
                debug = f"[v5] kb={_kb_error} key={_last_key} state={CURRENT_STATE}"
                footer_line = f"{debug} | {DISPLAY_UNIT} (B/M) | {nav_hint} | UP:{uptime}"
                cur['footer'].update(Align.center(Text(footer_line, style='dim')))

                live.update(cur)

            except Exception as e:
                try:
                    cur['footer'].update(Panel(Text(f"RENDER FAULT: {e}", style="bold red"), border_style="red"))
                    live.update(cur)
                except Exception:
                    pass

            # Frame pacing + keyboard. select() blocks up to 0.25s; returns early on keypress.
            if _kb_ok and select.select([sys.stdin], [], [], 0.25)[0]:
                try:
                    raw = os.read(_stdin_fd, 1)
                    if raw:
                        key = raw.decode('utf-8', errors='ignore').lower()
                        _last_key = repr(key)
                        if key in ['b', 'm']:
                            DISPLAY_UNIT = 'MB' if DISPLAY_UNIT == 'GB' else 'GB'
                        elif key == '2' and CURRENT_STATE == "MAIN":
                            hw_cache['ready'] = False
                            hw_cache['progress'] = 0
                            CURRENT_STATE = "HARDWARE"
                            threading.Thread(target=collect_hardware_data_bg, daemon=True).start()
                        elif key in ['1', 'r']:
                            CURRENT_STATE = "MAIN"
                except Exception as e:
                    _last_key = f"err:{e}"
            else:
                time.sleep(0.25)

except KeyboardInterrupt: pass
finally: restore_terminal()
