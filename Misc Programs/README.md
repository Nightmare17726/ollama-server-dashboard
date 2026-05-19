
```
 ██████╗ ██╗     ██╗      █████╗ ███╗   ███╗ █████╗     ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗ 
██╔═══██╗██║     ██║     ██╔══██╗████╗ ████║██╔══██╗    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗
██║   ██║██║     ██║     ███████║██╔████╔██║███████║    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝
██║   ██║██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗
╚██████╔╝███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
```

---

# Misc Programs

Standalone utility scripts that complement the main Ollama dashboard but run independently.

---

## `ram_check.py`

A command-line diagnostic tool for reading physical RAM topology directly from SMBIOS data via `dmidecode`. It reports every memory slot on the motherboard — populated or empty — with the installed module size, maximum slot capacity, speed, type, and vendor/part information.

Useful for verifying what the dashboard's Hardware Diagnostics view is reading, or for quickly auditing RAM configuration without launching the full dashboard.

### Requirements

- Python 3.9+
- `dmidecode` installed on the system
- **Must be run as root** (dmidecode requires raw SMBIOS access)

No additional Python packages are required beyond the standard library.

### Usage

```bash
sudo python3 ram_check.py
```

### Example Output

```
Motherboard: ASUS Sabertooth X79
Max Capacity: 64 GB across 8 slots (8 GB max per slot)

Slot          Status    Installed    Max     Speed       Type    Vendor
───────────────────────────────────────────────────────────────────────
DIMM_A1       Installed  8 GB       8 GB   1600 MT/s   DDR3    Kingston
DIMM_A2       Empty      —          8 GB   —           —       —
DIMM_B1       Installed  8 GB       8 GB   1600 MT/s   DDR3    Kingston
DIMM_B2       Empty      —          8 GB   —           —       —
DIMM_C1       Installed  8 GB       8 GB   1600 MT/s   DDR3    Kingston
DIMM_C2       Empty      —          8 GB   —           —       —
DIMM_D1       Installed  8 GB       8 GB   1600 MT/s   DDR3    Kingston
DIMM_D2       Empty      —          8 GB   —           —       —
```

Slots are listed in physical left-to-right order as reported by the SMBIOS locator strings.

### How It Works

The script calls `dmidecode` three times:

| dmidecode type | Data extracted |
|---|---|
| `-t 2` | Motherboard manufacturer and model |
| `-t 16` | Physical Memory Array — total max capacity and slot count |
| `-t 17` | Memory Device — per-slot installed size, speed, type, vendor, part number |

Max capacity per slot is calculated as `total_max_capacity / num_slots` from the Type 16 record. Each Type 17 record maps to one physical slot.

### Non-root / Windows Fallback

If the script is run without root privileges (or on Windows), it prints synthetic placeholder data so the output format can be verified without hardware access. A warning is displayed at the top of the output in this case.
