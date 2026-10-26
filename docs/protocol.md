# Nimbus HID protocol

Bluetooth classic, `0111:1420`. The input report is **17 bytes with no Report ID** and is sent only when the state changes. The layout was read from the controller's own HID descriptor, confirmed with captured reports, and cross-checked against the Nimbus mapping shipped with [MFIGamepadFeeder](https://github.com/Axadiw/MFIGamepadFeeder) (on Windows the first byte is a Report ID, so that tool's indices are shifted by one).

| Bytes | Field | Range |
|---|---|---|
| 0–3 | D-pad up, right, down, left | uint8, analog, rest 0 |
| 4–11 | A, B, X, Y, L1, R1, L2, R2 | uint8, all analog; L2/R2 reach 0…255 |
| 12 | bit 0 = Home/Menu | |
| 13–16 | left X, left Y, right X, right Y | int8 −127…127, **up is positive** |

Output report: 1 byte, no Report ID, low nibble = player LEDs (1, 2, 4, 8 = player 1 to 4). Through hidraw the report number goes first: `write(fd, [0x00, mask])`. Writing the mask alone fails with `EINVAL`. On iOS the host lights the LED of the player number when a game starts; the driver does the same on connect.

## Bluetooth SDP record

Read from the controller over L2CAP (PSM 1) with `tools/sdp_dump.py`. The services are not listed in the public browse group, so query them by UUID.

| Service | Notable attributes |
|---|---|
| HID `0x1124` | subclass `0x08` (gamepad), VirtualCable, ReconnectInitiate, BatteryPower, RemoteWake off, NormallyConnectable off, supervision timeout 2 s, SSR max latency 450 ms |
| PnP `0x1200` | vendor ID source Bluetooth SIG, vendor `0x0111` (SteelSeries), product `0x1420`, version `0x0001` |
| `00000000-deca-fade-deca-deafdecacaff` | Apple accessory protocol on RFCOMM channel 1 (MFi authentication for iOS, not needed for HID) |

## Hardware (FCC ID ZHK-GC-00004)

Model GC-00004, Bluetooth 4.1 BR/EDR without LE, 820 mAh Li-po, Lightning charging port. D-pad and face buttons sit on pressure-sensing membranes, which is why every button reports 0–255.

## Why the kernel gets it wrong

- The D-pad is four independent analog usages, a layout `hid-input` folds into a hat switch incorrectly, leaving `ABS_HAT0Y` stuck at −1.
- Every field is an 8-bit integer, so L2/R2 are mapped to buttons and their analog value is lost.
- `hid-steelseries` only covers the USB Nimbus (`1038`).

## Measuring a controller

```sh
nimbus-linux --monitor 30
```

prints every change and, at the end, the min and max seen for each byte.
