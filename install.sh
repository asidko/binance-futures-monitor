#!/bin/sh
# install.sh - fetch the latest bfm release binary for this OS/arch.
#   curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh -s -- --remove
set -e

REPO="asidko/binance-futures-monitor"
BIN="bfm"
INSTALL_DIR="${BFM_INSTALL_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/bfm"

detect_target() {
    os=$(uname -s)
    arch=$(uname -m)
    case "$os" in
        Linux) os=linux ;;
        Darwin) os=macos ;;
        *) echo "unsupported OS: $os" >&2; exit 1 ;;
    esac
    case "$arch" in
        x86_64|amd64) arch=x86_64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) echo "unsupported arch: $arch" >&2; exit 1 ;;
    esac
    echo "${os}-${arch}"
}

do_remove() {
    if [ -f "$INSTALL_DIR/$BIN" ]; then
        rm -f "$INSTALL_DIR/$BIN"
        echo "removed $INSTALL_DIR/$BIN"
    else
        echo "$BIN not installed in $INSTALL_DIR"
    fi
    echo "note: config and data left in $CONFIG_DIR (delete manually if unwanted)"
    exit 0
}

case "${1:-}" in
    --remove|remove|uninstall) do_remove ;;
esac

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

target=$(detect_target)
url="https://github.com/${REPO}/releases/latest/download/${BIN}-${target}"

mkdir -p "$INSTALL_DIR"
echo "downloading ${BIN}-${target}"
curl -fSL "$url" -o "$INSTALL_DIR/$BIN"
chmod 755 "$INSTALL_DIR/$BIN"
echo "installed $INSTALL_DIR/$BIN"

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *) echo "warning: $INSTALL_DIR is not in PATH - add it to your shell profile" ;;
esac

echo "done. run: $BIN --help"
echo "config is auto-created at $CONFIG_DIR/config.toml on first run (edit for Telegram)"
