#!/usr/bin/env bash
set -euo pipefail

corpus_dir="${1:?usage: bootstrap_fpc_runtime.sh CORPUS_DIR INSTALL_DIR HOST_FPC WORKERS}"
install_dir="${2:?usage: bootstrap_fpc_runtime.sh CORPUS_DIR INSTALL_DIR HOST_FPC WORKERS}"
host_fpc="${3:?usage: bootstrap_fpc_runtime.sh CORPUS_DIR INSTALL_DIR HOST_FPC WORKERS}"
workers="${4:?usage: bootstrap_fpc_runtime.sh CORPUS_DIR INSTALL_DIR HOST_FPC WORKERS}"

if [[ ! -e "$corpus_dir/.git" ]]; then
    echo "Pinned FPC corpus is not a Git checkout: $corpus_dir" >&2
    exit 1
fi
if [[ ! "$workers" =~ ^[1-9][0-9]*$ ]]; then
    echo "Worker count must be a positive integer: $workers" >&2
    exit 1
fi
if ! command -v "$host_fpc" >/dev/null 2>&1 && [[ ! -x "$host_fpc" ]]; then
    echo "Host FPC compiler is not executable: $host_fpc" >&2
    exit 1
fi
if [[ -e "$install_dir" ]] && [[ -n "$(find "$install_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Self-hosted FPC install directory must be empty: $install_dir" >&2
    exit 1
fi

git -C "$corpus_dir" sparse-checkout add compiler utils
make -C "$corpus_dir" "-j$workers" all "PP=$host_fpc"
make -C "$corpus_dir" install "INSTALL_PREFIX=$install_dir"

runtime_fpc="$install_dir/bin/sourcebridge-fpc"
mkdir -p "$(dirname "$runtime_fpc")"
cat > "$runtime_fpc" <<EOF
#!/usr/bin/env bash
exec "$corpus_dir/compiler/ppcx64" \\
    "-Fu$corpus_dir/rtl/units/x86_64-linux" "\$@"
EOF
chmod +x "$runtime_fpc"
if [[ ! -x "$runtime_fpc" ]]; then
    echo "Self-hosted FPC compiler was not installed: $runtime_fpc" >&2
    exit 1
fi
"$runtime_fpc" -iV
