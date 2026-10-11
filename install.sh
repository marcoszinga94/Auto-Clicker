#!/usr/bin/env bash
# Instala Auto Clicker Simple en el menú de aplicaciones del usuario.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin/autoclicker-simple"
APPS="$HOME/.local/share/applications"

mkdir -p "$(dirname "$BIN")" "$APPS"
install -m 0755 "$DIR/autoclicker.py" "$BIN"

cat > "$APPS/io.github.zinike.autoclickersimple.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Auto Clicker Simple
Comment=Auto clicker con botón y atajo global
Exec=python3 $BIN
Icon=input-mouse
Terminal=false
Categories=Utility;
EOF

update-desktop-database "$APPS" 2>/dev/null || true

echo "Instalado en: $BIN"
echo "Busca 'Auto Clicker Simple' en el menú de aplicaciones."
