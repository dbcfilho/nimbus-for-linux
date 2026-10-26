# Wine and old DirectInput games

## The `game` profile

Old games read the controller through DirectInput, usually setting each axis to a symmetric range (for example −10000…+10000). Two consequences:

- **A trigger that rests at its minimum reads as fully pushed.** The `game` profile therefore declares the trigger axes as −255…255. The controller reports 0…255, so rest sits at the center and the pull covers the upper half with every step preserved.
- **Merged triggers.** If SDL classifies the device as a gamepad (it has `BTN_SOUTH`, `BTN_EAST`, …), Wine builds an XInput-style device and DirectInput merges both triggers into one Z axis. The `game` profile places its buttons in the `BTN_JOYSTICK` range (`0x120…`), SDL then sees a plain joystick, and Wine exposes X, Y, Z, Rx, Ry and Rz as separate axes.

Spoofing an Xbox 360 identity does not help here, and `SDL_GAMECONTROLLER_IGNORE_DEVICES` makes Wine lose the device entirely.

## Case study: Need for Speed: Most Wanted (2005)

Setup: Wine-GE 8, Lutris, the ThirteenAG Widescreen Fix.

- All input goes through the *EZ Wheel Wrapper* module, which calls `DirectInput8Create` (version `0x800`) and sets each axis to −10000…+10000 (disassembly of `speed.exe`). That explains both symptoms above.
- With the `game` profile, the triggers show up as two independent axes in the controls screen. Wine names the axes itself ("Z Axis", "Z Rotation").
- **Remapping got stuck, and the labels read "LT / RT".** Both come from the Widescreen Fix: `ImproveGamepadSupport = 1` in `scripts/NFSMostWanted.WidescreenFix.ini` replaces input labels and assumes an XInput pad. Setting it to `0` made remapping work again in our tests. Keep a backup of the `.ini` before editing.

Lutris pre-launch / post-exit commands:

```
nimbus-profile game
nimbus-profile standard
```
