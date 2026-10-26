#!/bin/sh
# Instala o nimbus-linux para o usuário atual. Só a regra udev precisa de root (sudo).
#   ./install.sh              instala e liga o serviço
#   ./install.sh --uninstall  remove tudo
set -eu
cd "$(dirname "$0")"
BIN="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
RULE=/etc/udev/rules.d/70-nimbus-linux.rules

if [ "${1:-}" = "--uninstall" ]; then
  systemctl --user disable --now nimbus-linux.service 2>/dev/null || true
  rm -f "$BIN/nimbus-linux" "$BIN/nimbus-profile" "$UNIT_DIR/nimbus-linux.service"
  systemctl --user daemon-reload
  if [ -e "$RULE" ]; then sudo rm -f "$RULE" && sudo udevadm control --reload && sudo udevadm trigger; fi
  echo "removido (a configuração em ~/.config/nimbus-linux foi mantida)"
  exit 0
fi

command -v python3 >/dev/null || { echo "python3 não encontrado" >&2; exit 1; }
mkdir -p "$BIN" "$UNIT_DIR"
install -m 755 src/nimbus_linux.py "$BIN/nimbus-linux"
install -m 755 bin/nimbus-profile "$BIN/nimbus-profile"
install -m 644 systemd/nimbus-linux.service "$UNIT_DIR/nimbus-linux.service"

if ! cmp -s udev/70-nimbus-linux.rules "$RULE" 2>/dev/null; then
  echo "instalando a regra udev (pede sua senha)..."
  sudo install -m 644 udev/70-nimbus-linux.rules "$RULE"
  sudo rm -f /etc/udev/rules.d/98-nimbus-hide-raw.rules  # versão antiga, agora dentro da 70
  sudo udevadm control --reload
  sudo udevadm trigger --subsystem-match=hidraw --subsystem-match=input --subsystem-match=misc
fi

systemctl --user daemon-reload
systemctl --user enable nimbus-linux.service
systemctl --user restart nimbus-linux.service
echo "pronto. Ligue o Nimbus e veja: journalctl --user -u nimbus-linux -f"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "aviso: $BIN não está no PATH" ;; esac
