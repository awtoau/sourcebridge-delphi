#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(source /etc/os-release && printf '%s' "$ID")" != "fedora" ]]; then
    echo "This bootstrap script supports Fedora only." >&2
    exit 1
fi

sudo dnf install -y fpc

cd "$repository_root"
python3 tools/toolchain_report.py
python3 tools/validate_fpc_fixture.py
python3.15t -m unittest discover -s tests -v
