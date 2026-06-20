#!/bin/sh
# install.sh - fetch a bfm release binary for this OS/arch (latest by default).
#   curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh
#   curl -fsSL .../install.sh | sh -s -- --tag v1.0.0     # pin a version
#   curl -fsSL .../install.sh | sh -s -- --remove
set -e

REPO="asidko/binance-futures-monitor"
BIN="bfm"
INSTALL_DIR="${BFM_INSTALL_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/bfm"
TAG=""

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

while [ $# -gt 0 ]; do
    case "$1" in
        --remove|remove|uninstall) do_remove ;;
        --tag) TAG="$2"; shift 2 ;;
        --tag=*) TAG="${1#--tag=}"; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

target=$(detect_target)
if [ -n "$TAG" ]; then
    url="https://github.com/${REPO}/releases/download/${TAG}/${BIN}-${target}"
else
    url="https://github.com/${REPO}/releases/latest/download/${BIN}-${target}"
fi

mkdir -p "$INSTALL_DIR"
echo "downloading ${BIN}-${target} (${TAG:-latest})"
curl -fSL "$url" -o "$INSTALL_DIR/$BIN"
chmod 755 "$INSTALL_DIR/$BIN"
# macOS: strip the Gatekeeper quarantine flag so the binary runs without a prompt
# (a no-op when the flag is absent, e.g. plain curl downloads)
[ "$(uname -s)" = "Darwin" ] && xattr -d com.apple.quarantine "$INSTALL_DIR/$BIN" 2>/dev/null || true
echo "installed $INSTALL_DIR/$BIN"

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *) echo "warning: $INSTALL_DIR is not in PATH - add it to your shell profile" ;;
esac

echo "done. run: $BIN --help"
echo "config is auto-created at $CONFIG_DIR/config.toml on first run (edit for Telegram)"
