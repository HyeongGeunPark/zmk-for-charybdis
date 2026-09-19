# ZMK config for Charybdis (4x6)

Personal ZMK configuration for a wireless Charybdis 4x6 split keyboard with a
PMW3610 trackball on the right half.

The current configuration targets the Zephyr 4.1 based, pre-v0.4 ZMK line.
Keyboard, split BLE, USB, Studio, and standard mouse-button behaviors are
verified on hardware. The legacy PMW3610 module has been dropped for good; the
trackball is being rebuilt on [badjeff/zmk-pmw3610-driver][pmw] together with
ZMK's input processors, so the old `PMW_*` keymap bindings will not return.

[pmw]: https://github.com/badjeff/zmk-pmw3610-driver

## Documentation

- [Dongle and ESB research](docs/dongle-esb-research.md)
- [Dongle and ESB migration plan](docs/dongle-esb-migration.md)
