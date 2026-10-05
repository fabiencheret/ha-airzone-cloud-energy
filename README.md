# Airzone Cloud (Energy Clamp) for Home Assistant

Custom integration that overrides the built-in `airzone_cloud` integration (same domain) and adds
sensors for the Airzone energy clamp (`az_energy_clamp`): power, energy consumed, energy returned,
current and voltage.

It is based on the Home Assistant core `airzone_cloud` integration (2026.9.4) and depends on the
`feature/energy-clamp` branch of [aioairzone-cloud](https://github.com/fabiencheret/aioairzone-cloud).

## Install with HACS

1. HACS → ⋮ → Custom repositories → add this repository, type **Integration**.
2. Install **Airzone Cloud (Energy Clamp)** and restart Home Assistant.
3. Your existing Airzone Cloud config entry keeps working; the clamp appears as a new
   "Energy Clamp" device.

The container needs `git` and internet access to install the library from GitHub.

## Notes

- Energy sensors use `total_increasing`, so they can be selected in the Energy dashboard.
- Power is reported in W by the API (checked against current and voltage); current and voltage are diagnostic entities.
- Home Assistant logs a warning that this overrides the core integration. That is expected.
- Licensed under Apache 2.0, like Home Assistant core.
