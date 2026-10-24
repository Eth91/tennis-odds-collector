#!/bin/bash
# Deploy the NCAAF pre-kick collector CODE to the VM. Never copies data.
set -eu
VM=ubuntu@155.248.217.149
KEY=$HOME/.ssh/oracle_vm
SRC=$(cd "$(dirname "$0")/.." && pwd)
ssh -i "$KEY" "$VM" 'mkdir -p ~/ncaaf-prekick/data ~/ncaaf-prekick/logs'
rsync -a -e "ssh -i $KEY" "$SRC/fd_props.py" "$SRC/vm_prekick/run.sh" "$SRC/vm_prekick/export.py" "$VM:ncaaf-prekick/"
ssh -i "$KEY" "$VM" 'chmod +x ~/ncaaf-prekick/run.sh && cd ~/ncaaf-prekick && /usr/bin/python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in (\"fd_props.py\",\"export.py\")]; print(\"deployed ok\")"'
