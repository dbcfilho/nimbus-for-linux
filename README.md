# nimbus-for-linux

Native Linux support for the **SteelSeries Nimbus** (Bluetooth, MFi) game controller.

[Português](README.pt-BR.md)

The Nimbus is built for Apple devices. On Linux the stock `hid-generic` driver mishandles it:

- the D-pad is stuck on "up" (`ABS_HAT0Y = -1` forever);
- the analog triggers (L2/R2) are flattened into on/off buttons;
- Steam, SDL and Wine games end up with a controller that is half broken.

`nimbus-for-linux` fixes this in user space. It reads the controller's raw HID reports and exposes a correct virtual gamepad through `uinput`. It is pure Python (standard library only), needs no kernel module and no root at run time.

| | stock kernel | nimbus-for-linux |
|---|---|---|
| D-pad | stuck on up | works |
| L2 / R2 | on/off buttons | analog, 0–255 |
| Sticks | working | working |
| L3 / R3 / Back | not available | via Home combos |
| Player LED | off | player 1 lit on connect |

## Install

```sh
git clone https://github.com/dbcfilho/nimbus-for-linux.git
cd nimbus-for-linux
./install.sh
```

Requirements: Linux with `uinput`, systemd, Python ≥ 3.8 and `sudo` (once, to install the udev rule). Pair the controller with Bluetooth as usual, then watch it connect:

```sh
journalctl --user -u nimbus-linux -f
```

Remove everything with `./install.sh --uninstall`.

## Button layout

| Nimbus | Virtual pad |
|---|---|
| A, B, X, Y, L1, R1 | A, B, X, Y, LB, RB |
| L2, R2 (analog) | LT, RT (analog) |
| Home | Start |
| L1 + Home | L3 (left stick click) |
| R1 + Home | R3 (right stick click) |
| L1 + R1 + Home | Back / Select |

The Home combinations follow the mapping used by [MFIGamepadFeeder](https://github.com/Axadiw/MFIGamepadFeeder), the Windows tool that does the same job there.

## Profiles

| Profile | Presents itself as | Use it for |
|---|---|---|
| `standard` (default) | Xbox 360 pad (`045e:028e`), xpad layout | Steam, SDL, Proton, emulators |
| `game` | raw joystick (`0111:1420`), buttons in the `BTN_JOYSTICK` range, triggers centered | old DirectInput games under Wine |

```sh
nimbus-profile          # show the current profile
nimbus-profile game     # switch; the running daemon reloads on SIGHUP, no reconnect needed
```

With Lutris, set `nimbus-profile game` as the pre-launch command and `nimbus-profile standard` as the post-exit command.

## Wine and old DirectInput games

Two things go wrong with a normal gamepad in old DirectInput games:

1. DirectInput sets every axis to a symmetric range, so a trigger that rests at its minimum reads as fully pushed. The `game` profile declares the trigger range as −255…255 and rests at the center, so the pull spans 0…255 without losing steps.
2. When SDL classifies the device as a gamepad, Wine merges both triggers into a single Z axis. The `game` profile uses `BTN_JOYSTICK` buttons so SDL treats it as a plain joystick and Wine exposes six independent axes.

Details, including a case study on *Need for Speed: Most Wanted* (2005), are in [docs/wine-games.md](docs/wine-games.md).

## Options

`nimbus-linux --help`. The main ones: `--profile`, `--identity`, `--home start|mode`, `--flip-y`, `--no-grab`, `--led MASK`, and `--monitor SECONDS`, which prints the raw reports and the min/max of every byte (useful for porting another controller).

## Protocol

17-byte input report, no Report ID, sent only when something changes. See [docs/protocol.md](docs/protocol.md).

## Known limitations

- Tested on one controller and one setup (Debian 13, kernel 7.1, Wine-GE 8). Reports from other distributions and Nimbus revisions are welcome.
- The Nimbus+ and USB variants use different IDs and are not covered.

## Development

```sh
python3 -m unittest discover -s tests -v
```

The report → events conversion is a pure function (`translate`) and is unit tested. Everything else talks to `/dev/uinput` and hidraw and needs the controller.

## License

MIT, see [LICENSE](LICENSE).
