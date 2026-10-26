# Nimbus HID protocol

Bluetooth classic, `0111:1420`. The input report is **17 bytes with no Report ID** and is sent only when the state changes. The layout was read from the controller's own HID descriptor, confirmed with captured reports, and cross-checked against the Nimbus mapping shipped with [MFIGamepadFeeder](https://github.com/Axadiw/MFIGamepadFeeder) (on Windows the first byte is a Report ID, so that tool's indices are shifted by one).

| Bytes | Field | Range |
|---|---|---|
| 0–3 | D-pad up, right, down, left | uint8, analog, rest 0 |
| 4–11 | A, B, X, Y, L1, R1, L2, R2 | uint8, all analog; L2/R2 reach 0…255 |
| 12 | bit 0 = Home/Menu | |
| 13–16 | left X, left Y, right X, right Y | int8 −127…127, **up is positive** |

Output report: 1 byte, low nibble = player LEDs. Writing it through hidraw fails with `EINVAL`.

## Why the kernel gets it wrong

- The D-pad is four independent analog usages, a layout `hid-input` folds into a hat switch incorrectly, leaving `ABS_HAT0Y` stuck at −1.
- Every field is an 8-bit integer, so L2/R2 are mapped to buttons and their analog value is lost.
- `hid-steelseries` only covers the USB Nimbus (`1038`).

## Measuring a controller

```sh
nimbus-linux --monitor 30
```

prints every change and, at the end, the min and max seen for each byte.
