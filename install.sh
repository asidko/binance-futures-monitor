#!/bin/sh
# install.sh - fetch a bfm release binary for this OS/arch (latest by default).
# Termux (Android, bionic): arm64 has a prebuilt binary; other arches install from source.
#   curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh
#   curl -fsSL .../install.sh | sh -s -- --tag v1.0.0     # pin a version
#   curl -fsSL .../install.sh | sh -s -- --remove
set -eu

REPO="asidko/binance-futures-monitor"
BIN="bfm"
INSTALL_DIR="${BFM_INSTALL_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/bfm"
TAG=""
OS=$(uname -s)
TERMUX_LIB="${PREFIX:-}/share/bfm"

is_termux() {
    case "${PREFIX:-}" in *com.termux*) return 0 ;; esac
    [ -n "${TERMUX_VERSION:-}" ]
}

# Termux is Android/bionic - the glibc release binaries can't run there. Install from source
# instead and drop a shim that runs it with Termux's Python; bfm needs requests, the rest is stdlib.
install_termux() {
    command -v python3 >/dev/null 2>&1 || { echo "python3 missing - run: pkg install python" >&2; exit 1; }
    python3 -c "import requests" >/dev/null 2>&1 || pip install --no-input requests
    ref="${TAG:-main}"
    raw="https://raw.githubusercontent.com/${REPO}/${ref}"
    bindir="${BFM_INSTALL_DIR:-$PREFIX/bin}"
    mkdir -p "$bindir" "$TERMUX_LIB"
    echo "Termux: installing bfm from source (${ref})"
    for f in main.py daemon.py store.py proclock.py paths.py conditions.py binance_client.py config.py notifier.py version.py; do
        curl -fSL "$raw/src/$f" -o "$TERMUX_LIB/$f"
    done
    printf '#!%s/bin/sh\nexec python3 "%s/main.py" "$@"\n' "$PREFIX" "$TERMUX_LIB" > "$bindir/$BIN"
    chmod 755 "$bindir/$BIN"
    "$bindir/$BIN" --help >/dev/null 2>&1 || true
    echo "installed $bindir/$BIN"
    echo "config at $CONFIG_DIR/config.toml (edit for Telegram alerts)"
    echo "done. run: $BIN --help"
    exit 0
}

detect_target() {
    arch=$(uname -m)
    if is_termux; then
        os=android
    else
        case "$OS" in
            Linux) os=linux ;;
            Darwin) os=macos ;;
            *) echo "unsupported OS: $OS" >&2; exit 1 ;;
        esac
    fi
    case "$arch" in
        x86_64|amd64) arch=x86_64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) echo "unsupported arch: $arch" >&2; exit 1 ;;
    esac
    echo "${os}-${arch}"
}

do_remove() {
    if is_termux; then
        bin_path="${BFM_INSTALL_DIR:-$PREFIX/bin}/$BIN"
    else
        bin_path="$INSTALL_DIR/$BIN"
    fi
    # stop the daemon BEFORE deleting the binary - it never exits on its own
    # while watches are active, and `bfm stop` is gone once the file is
    [ -x "$bin_path" ] && "$bin_path" stop >/dev/null 2>&1 || true
    if is_termux; then
        rm -f "$bin_path"
        rm -rf "$TERMUX_LIB"
        echo "removed $BIN (Termux)"
    elif [ -f "$bin_path" ]; then
        rm -f "$bin_path"
        echo "removed $bin_path"
    else
        echo "$BIN not installed in $INSTALL_DIR"
    fi
    case "$OS" in
        Darwin) cache="$HOME/Library/Caches/$BIN" ;;
        *) cache="${XDG_CACHE_HOME:-$HOME/.cache}/$BIN" ;;
    esac
    echo "note: config and data left in $CONFIG_DIR, unpack cache in $cache (delete manually if unwanted)"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --remove|remove|uninstall) do_remove ;;
        --tag) [ $# -ge 2 ] || { echo "--tag needs a value" >&2; exit 2; }; TAG="$2"; shift 2 ;;
        --tag=*) TAG="${1#--tag=}"; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

# Termux arm64 has a prebuilt binary (built in CI under the Termux image); other Termux arches build from source
if is_termux; then
    INSTALL_DIR="${BFM_INSTALL_DIR:-$PREFIX/bin}"
    case "$(uname -m)" in
        aarch64|arm64) ;;
        *) install_termux ;;
    esac
fi

target=$(detect_target)
if [ "$target" = "macos-x86_64" ]; then
    echo "no prebuilt binary for Intel macOS - build from source: https://github.com/${REPO}#develop--build-from-source" >&2
    exit 1
fi
if [ -n "$TAG" ]; then
    base="https://github.com/${REPO}/releases/download/${TAG}"
else
    base="https://github.com/${REPO}/releases/latest/download"
fi

asset="${BIN}-${target}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "downloading ${asset} (${TAG:-latest})"
if ! curl -fSL "$base/$asset" -o "$tmp/$asset"; then
    if is_termux; then
        # a release may ship without the android asset (its build is best-effort)
        echo "no prebuilt $asset in this release - falling back to source install"
        install_termux
    fi
    echo "download failed: $base/$asset" >&2
    exit 1
fi
curl -fSL "$base/SHA256SUMS" -o "$tmp/SHA256SUMS"

# verify the download against the release checksum before trusting the binary
want=$(awk -v f="$asset" '$2 == f {print $1}' "$tmp/SHA256SUMS")
[ -n "$want" ] || { echo "no checksum for $asset in SHA256SUMS" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
    got=$(sha256sum "$tmp/$asset" | awk '{print $1}')
else
    got=$(shasum -a 256 "$tmp/$asset" | awk '{print $1}')
fi
[ "$want" = "$got" ] || { echo "checksum mismatch for $asset" >&2; exit 1; }
echo "checksum ok"

mkdir -p "$INSTALL_DIR"
# stage INSIDE the install dir: chmod + de-quarantine the staged copy, then a
# same-filesystem mv (atomic rename) - the live binary is never truncated
# mid-write and a running daemon keeps its old inode
staged="$INSTALL_DIR/.$BIN.new"
mv "$tmp/$asset" "$staged"
chmod 755 "$staged"
# macOS: strip the Gatekeeper quarantine flag so the binary runs without a prompt
# (matters for browser-downloaded binaries; a no-op for plain curl downloads)
if [ "$OS" = "Darwin" ]; then
    xattr -d com.apple.quarantine "$staged" 2>/dev/null || true
fi
mv -f "$staged" "$INSTALL_DIR/$BIN"
echo "installed $INSTALL_DIR/$BIN"

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *) echo "warning: $INSTALL_DIR is not in PATH - add it to your shell profile" ;;
esac

echo "running first-time setup (unpacks the binary, may take a moment)..."
if ! "$INSTALL_DIR/$BIN" --version; then
    echo "warning: $BIN did not run on this system - check OS/arch compatibility" >&2
fi
echo "config created at $CONFIG_DIR/config.toml (edit for Telegram alerts)"
echo "done. run: $BIN --help"
