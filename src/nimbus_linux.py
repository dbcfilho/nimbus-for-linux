#!/usr/bin/env python3
"""nimbus-linux: driver em espaço de usuário para o SteelSeries Nimbus (Bluetooth, 0111:1420).

O Nimbus fala HID cru (17 bytes por relatório, sem Report ID). O hid-generic do kernel
não entende o layout: achata os gatilhos em botões e sintetiza o D-pad errado. Este
daemon lê o relatório bruto via hidraw e expõe um gamepad evdev (uinput).

Layout do relatório (descritor HID lido do próprio controle):
  [0..3]   D-pad Up, Right, Down, Left   (uint8, 0..255)
  [4..11]  A, B, X, Y, L1, R1, L2, R2    (uint8, 0..255; L2/R2 são analógicos)
  [12]     bit0 = Home/Menu (Consumer AC Home); sozinho vira Start
           L1+Home = L3, R1+Home = R3, L1+R1+Home = Back (como no MFIGamepadFeeder)
  [13..16] stick esq X, esq Y, dir X, dir Y (int8, -127..127; cima = positivo)
Relatório de saída (1 byte): nibble baixo = LEDs de jogador.

Perfis do gamepad virtual:
  standard  identidade Xbox 360, layout do xpad (SDL, Steam, Proton, emuladores)
  game      joystick cru, gatilhos centralizados (jogos DirectInput antigos via Wine)
"""
import argparse
import fcntl
import glob
import os
import select
import signal
import struct
import sys
import time

__version__ = "1.0.0"

VID, PID = 0x0111, 0x1420
HID_ID = "HID_ID=0005:%08X:%08X" % (VID, PID)
REPORT_LEN = 17

# linux/uinput.h, linux/input.h, linux/input-event-codes.h
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
UI_DEV_SETUP, UI_ABS_SETUP = 0x405C5503, 0x401C5504
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
EVIOCGRAB = 0x40044590
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x133, 0x134
BTN_TL, BTN_TR, BTN_SELECT, BTN_START, BTN_MODE = 0x136, 0x137, 0x13A, 0x13B, 0x13C
BTN_THUMBL, BTN_THUMBR = 0x13D, 0x13E
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y = 0, 1, 2, 3, 4, 5, 16, 17

DPAD_ON = 0x40  # D-pad é analógico 0..255; acima disso conta como pressionado
PROFILES = ("standard", "game")
PROFILE_FILE = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "nimbus-linux", "profile")

IDENTITIES = {
    # mesmo VID:PID/versão do xpad: SDL, Steam e Proton já têm mapeamento pronto
    "xbox360": (0x03, 0x045E, 0x028E, 0x0114, b"Nimbus (Xbox 360 virtual)"),
    "nimbus": (0x05, VID, PID, 0x0001, b"Nimbus (nativo)"),
}

# índice no relatório -> botão evdev. No perfil game os botões ficam na faixa BTN_JOYSTICK (0x120..):
# sem BTN_SOUTH/EAST/... o SDL não classifica o dispositivo como gamepad, e o Wine passa os eixos
# crus em vez de fundir os gatilhos num Z "XInput".
BUTTONS = {
    "standard": ((4, BTN_SOUTH), (5, BTN_EAST), (6, BTN_NORTH), (7, BTN_WEST), (8, BTN_TL), (9, BTN_TR)),
    "game": ((4, 0x120), (5, 0x121), (6, 0x122), (7, 0x123), (8, 0x124), (9, 0x125)),
}
HOME_CODES = {"start": BTN_START, "mode": BTN_MODE}
GAME_HOME = 0x126
GAME_BACK, GAME_THUMBL, GAME_THUMBR = 0x127, 0x128, 0x129
STANDARD_KEYS = (BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR,
                 BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR)


def log(msg):
    print(msg, flush=True)


def stick(v):
    """int8 do relatório -> faixa de 16 bits do evdev."""
    return max(-32768, min(32767, round(v * 32767 / 127)))


def read_profile(path=PROFILE_FILE):
    try:
        with open(path) as f:
            name = f.read().strip()
    except OSError:
        return "standard"
    return name if name in PROFILES else "standard"


def key_codes(profile):
    if profile == "game":
        return [c for _, c in BUTTONS["game"]] + [GAME_HOME, GAME_BACK, GAME_THUMBL, GAME_THUMBR]
    return list(STANDARD_KEYS)


def abs_setup(profile):
    """(código, min, max, fuzz, flat) de cada eixo do gamepad virtual."""
    # DirectInput trata o repouso no mínimo como eixo empurrado até o fim; com faixa -255..255
    # o repouso (0) fica no centro e o puxão vai de 0 a 255 sem perder passos
    tlo = -255 if profile == "game" else 0
    return ((ABS_X, -32768, 32767, 16, 128), (ABS_Y, -32768, 32767, 16, 128),
            (ABS_RX, -32768, 32767, 16, 128), (ABS_RY, -32768, 32767, 16, 128),
            (ABS_Z, tlo, 255, 0, 0), (ABS_RZ, tlo, 255, 0, 0),
            (ABS_HAT0X, -1, 1, 0, 0), (ABS_HAT0Y, -1, 1, 0, 0))


def translate(r, profile, home="start", flip_y=False):
    """Relatório bruto de 17 bytes -> lista de (tipo, código, valor) evdev. Função pura."""
    pressed = {idx: bool(r[idx]) for idx, _ in BUTTONS[profile]}
    menu = bool(r[12] & 1)
    back = thumbl = thumbr = False
    if menu and (profile == "game" or home == "start"):
        # o Nimbus só tem um botão de menu; o driver original (MFIGamepadFeeder) cria o resto por
        # combinação: L1+Home = L3, R1+Home = R3, L1+R1+Home = Back. A combinação consome os botões.
        l1, r1 = pressed[8], pressed[9]
        if l1 and r1:
            back = True
        elif l1:
            thumbl = True
        elif r1:
            thumbr = True
        if l1 or r1:
            menu = False
            pressed[8] = pressed[9] = False
    ev = [(EV_KEY, code, int(pressed[idx])) for idx, code in BUTTONS[profile]]
    if profile == "game":
        ev += [(EV_KEY, GAME_HOME, int(menu)), (EV_KEY, GAME_BACK, int(back)),
               (EV_KEY, GAME_THUMBL, int(thumbl)), (EV_KEY, GAME_THUMBR, int(thumbr))]
    else:
        ev += [(EV_KEY, HOME_CODES[home], int(menu)), (EV_KEY, BTN_SELECT, int(back)),
               (EV_KEY, BTN_THUMBL, int(thumbl)), (EV_KEY, BTN_THUMBR, int(thumbr))]
    ev.append((EV_ABS, ABS_Z, r[10]))
    ev.append((EV_ABS, ABS_RZ, r[11]))
    up, right, down, left = (r[i] >= DPAD_ON for i in range(4))
    ev.append((EV_ABS, ABS_HAT0X, int(right) - int(left)))
    ev.append((EV_ABS, ABS_HAT0Y, int(down) - int(up)))
    lx, ly, rx, ry = struct.unpack("4b", bytes(r[13:17]))
    # o Nimbus manda cima positivo; evdev e SDL esperam cima negativo
    sy = 1 if flip_y else -1
    ev += [(EV_ABS, ABS_X, stick(lx)), (EV_ABS, ABS_Y, stick(sy * ly)),
           (EV_ABS, ABS_RX, stick(rx)), (EV_ABS, ABS_RY, stick(sy * ry))]
    return ev


def find_device():
    """Retorna (hidraw, evdev|None) do Nimbus conectado, ou None."""
    for p in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(p + "/device/uevent") as f:
                if HID_ID not in f.read():
                    continue
        except OSError:
            continue
        ev = sorted(glob.glob(p + "/device/input/input*/event*"))
        return "/dev/" + os.path.basename(p), ("/dev/input/" + os.path.basename(ev[0]) if ev else None)
    return None


class VirtualPad:
    def __init__(self, profile, identity, home="start", flip_y=False):
        self.profile, self.home, self.flip_y = profile, home, flip_y
        bus, vid, pid, ver, name = IDENTITIES[identity]
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            for code in key_codes(profile):
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            for code, lo, hi, fuzz, flat in abs_setup(profile):
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
                fcntl.ioctl(self.fd, UI_ABS_SETUP, struct.pack("<H2x6i", code, 0, lo, hi, fuzz, flat, 0))
            fcntl.ioctl(self.fd, UI_DEV_SETUP, struct.pack("<HHHH80sI", bus, vid, pid, ver, name, 0))
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        self.state = {}

    def _emit(self, etype, code, value):
        if self.state.get((etype, code)) == value:
            return
        self.state[(etype, code)] = value
        os.write(self.fd, struct.pack("<qqHHi", 0, 0, etype, code, value))

    def update(self, r):
        for etype, code, value in translate(r, self.profile, self.home, self.flip_y):
            self._emit(etype, code, value)
        os.write(self.fd, struct.pack("<qqHHi", 0, 0, EV_SYN, 0, 0))

    def release(self):
        """Solta tudo (controle desconectou) para não deixar botão preso."""
        self.update(bytes(REPORT_LEN))

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


class Daemon:
    def __init__(self, args):
        self.args = args
        self.stop = False
        self.reload = False

    def config(self):
        """(perfil, identidade) vigentes: opções da linha de comando valem mais que o arquivo."""
        profile = self.args.profile or read_profile()
        identity = self.args.identity or ("nimbus" if profile == "game" else "xbox360")
        return profile, identity

    def make_pad(self):
        profile, identity = self.config()
        pad = VirtualPad(profile, identity, self.args.home, self.args.flip_y)
        log("gamepad virtual: perfil %s (%s)" % (profile, identity))
        return pad

    def session(self, hidraw, evdev):
        hfd = os.open(hidraw, os.O_RDWR | os.O_NONBLOCK)
        efd = pad = None
        try:
            if evdev and not self.args.no_grab:
                try:  # esconde o nó quebrado do hid-generic dos apps
                    efd = os.open(evdev, os.O_RDONLY | os.O_NONBLOCK)
                    fcntl.ioctl(efd, EVIOCGRAB, 1)
                except OSError as e:
                    log("aviso: não consegui EVIOCGRAB em %s: %s" % (evdev, e))
            pad = self.make_pad()
            log("conectado: %s" % hidraw)
            if self.args.led:
                try:
                    os.write(hfd, bytes([self.args.led & 0x0F]))
                except OSError as e:
                    log("aviso: LED não aceito: %s" % e)
            while not self.stop:
                if self.reload:  # SIGHUP: troca de perfil sem derrubar a conexão com o controle
                    self.reload = False
                    pad.release()
                    pad.close()
                    pad = None
                    pad = self.make_pad()
                ready, _, _ = select.select([hfd] + ([efd] if efd is not None else []), [], [], 1.0)
                if efd is not None and efd in ready:
                    try:
                        while os.read(efd, 4096):  # drena o evdev agarrado
                            pass
                    except BlockingIOError:
                        pass
                if hfd in ready:
                    data = os.read(hfd, 64)
                    if len(data) == REPORT_LEN:
                        pad.update(data)
        except OSError as e:
            log("desconectado (%s)" % (e.strerror or e))
        finally:
            if pad is not None:
                try:
                    pad.release()
                except OSError:
                    pass
                pad.close()
            os.close(hfd)
            if efd is not None:
                os.close(efd)

    def run(self):
        def on_term(*_):
            self.stop = True

        def on_hup(*_):
            self.reload = True
        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
        signal.signal(signal.SIGHUP, on_hup)
        log("aguardando o Nimbus...")
        while not self.stop:
            dev = find_device()
            if dev:
                try:
                    self.session(*dev)
                except OSError as e:
                    log("erro: %s: %s" % (e.filename or "", e.strerror or e))
                    time.sleep(4.0)  # permissão ou uinput ausente: não ficar martelando
            time.sleep(1.0)


NAMES = ["dpad_up", "dpad_right", "dpad_down", "dpad_left", "A", "B", "X", "Y", "L1", "R1",
         "L2", "R2", "home", "stickL_x", "stickL_y", "stickR_x", "stickR_y"]


def monitor(seconds):
    """Mostra o relatório bruto e o min/max de cada byte; serve para validar o protocolo."""
    dev = find_device()
    if not dev:
        sys.exit("Nimbus não encontrado (ligue o controle).")
    hfd = os.open(dev[0], os.O_RDONLY | os.O_NONBLOCK)
    lo, hi, n, end = [999] * REPORT_LEN, [-999] * REPORT_LEN, 0, time.time() + seconds
    value = lambda d, i: struct.unpack("b", d[i:i + 1])[0] if i >= 13 else d[i]
    last = None
    try:
        while time.time() < end:
            r, _, _ = select.select([hfd], [], [], 0.2)
            if not r:
                continue
            d = os.read(hfd, 64)
            if len(d) != REPORT_LEN:
                print("relatório inesperado (%d bytes): %s" % (len(d), d.hex(" ")))
                continue
            n += 1
            for i in range(REPORT_LEN):
                lo[i], hi[i] = min(lo[i], value(d, i)), max(hi[i], value(d, i))
            if d != last:
                sig = " ".join("%s=%d" % (NAMES[i], value(d, i)) for i in range(REPORT_LEN) if d[i])
                print("%.2f  %s" % (end - time.time(), sig or "(tudo zero)"))
                last = d
    finally:
        os.close(hfd)
    print("\n%d relatórios. min/max (sticks em int8):" % n)
    for i, name in enumerate(NAMES):
        print("  [%2d] %-11s %4d .. %4d" % (i, name, lo[i], hi[i]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--profile", choices=PROFILES, default=None,
                    help="standard: Xbox 360 (SDL, Steam, emuladores); game: joystick cru com gatilhos "
                         "centralizados (DirectInput via Wine). Sem a opção, lê %s (escrito por "
                         "nimbus-profile) e recarrega com SIGHUP" % PROFILE_FILE)
    ap.add_argument("--identity", choices=IDENTITIES, default=None,
                    help="padrão: xbox360 no perfil standard, nimbus no perfil game")
    ap.add_argument("--home", choices=tuple(HOME_CODES), default="start",
                    help="botão evdev do Home/Menu do Nimbus no perfil standard (padrão: start)")
    ap.add_argument("--flip-y", action="store_true",
                    help="não inverte o Y dos analógicos (o padrão já converte cima-positivo para evdev)")
    ap.add_argument("--led", type=int, default=0,
                    help="máscara dos LEDs de jogador (0 = não mexer; o hidraw costuma recusar com EINVAL)")
    ap.add_argument("--no-grab", action="store_true", help="não esconder o nó evdev original")
    ap.add_argument("--monitor", type=int, metavar="SEG", help="só observa o relatório bruto por SEG segundos")
    args = ap.parse_args(argv)
    if args.monitor:
        return monitor(args.monitor)
    Daemon(args).run()


if __name__ == "__main__":
    main()
