cat << 'EOF' > ~/start_dash.sh
#!/bin/bash
# Force ROCm to recognize the RX 570 for this session
export HSA_OVERRIDE_GFX_VERSION=8.0.3

# Navigate to your dashboard directory
cd /home/chase/ollama_dash

# Run the dashboard using the virtual environment's python
# This avoids the "command not found" issues seen in image_27.png
./venv/bin/python advanced_dash.py
EOF

# Ensure the script has permission to run
chmod +x ~/start_dash.sh