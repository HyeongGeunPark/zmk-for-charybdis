# ZMK config for Charybdis (4x6)

Personal ZMK configuration for a wireless Charybdis 4x6 split keyboard with a
PMW3610 trackball on the right half.

It runs as a dongle plus two peripherals on the Zephyr 4.1 based, pre-v0.4 ZMK
line. Split traffic goes over ESB rather than BLE, putting the hop between the
halves and the dongle at roughly 1 ms. The dongle reaches the host over USB
only: there is no host Bluetooth, because the ESB module cannot be compiled
alongside it.

The trackball runs on [badjeff/zmk-pmw3610-driver][pmw]. Snipe and drag scroll
are layer-swapped input processor chains on the dongle rather than driver
features, so the old `PMW_*` keymap bindings are gone.

[pmw]: https://github.com/badjeff/zmk-pmw3610-driver

## Firmware

Two identical keyboard sets are built. They differ only in their ESB address,
which is what lets them be powered on near each other: ESB has no pairing, so
two sets sharing an address would have each dongle accepting the other's
halves. Set A's address lives in `charybdis_layout.dtsi`, set B's in
`config/esb_set_b.overlay`.

Each UF2 is named `set_<a|b>-charybdis_<role>`. Keep a set's three boards on
the same set — a half flashed from the wrong one simply never connects, and
nothing on the keyboard says why.

Flash `settings_reset` on a board before its first firmware.

## Documentation

- [Dongle and ESB research](docs/dongle-esb-research.md)
- [Dongle and ESB migration plan](docs/dongle-esb-migration.md)
