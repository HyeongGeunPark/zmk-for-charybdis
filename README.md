# ZMK config for Charybdis (4x6)

Personal ZMK configuration for a wireless Charybdis 4x6 split keyboard with a
PMW3610 trackball on the right half.

It runs as a dongle plus two peripherals on the Zephyr 4.1 based, pre-v0.4 ZMK
line. The dongle is the only central and reaches the host over USB, with ZMK
Studio on the same link; both halves talk to it over BLE split.

Split ran on ESB for a while, which cut the hop from roughly 7.5 ms to 1 ms.
That was reverted: the ESB module has no encryption or authentication, so key
positions travelled in the clear and nothing stopped injected or replayed
packets. BLE split bonds and encrypts. The ESB work is kept on the `esb`
branch and the `esb-dongle-verified` tag in case that changes.

The trackball runs on [badjeff/zmk-pmw3610-driver][pmw]. Snipe and drag scroll
are layer-swapped input processor chains on the dongle rather than driver
features, so the old `PMW_*` keymap bindings are gone.

[pmw]: https://github.com/badjeff/zmk-pmw3610-driver

## Firmware

Four targets: `charybdis_dongle`, `charybdis_left`, `charybdis_right`, and
`settings_reset`. Flash `settings_reset` on a board before its first firmware.

A second keyboard set needs no configuration of its own. BLE bonding keeps
sets apart, so two of them can sit side by side — which was not true on ESB,
where the address had to be managed by hand.

## Documentation

- [Dongle and ESB research](docs/dongle-esb-research.md)
- [Dongle and ESB migration plan](docs/dongle-esb-migration.md)
