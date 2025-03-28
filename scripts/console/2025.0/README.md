# `topology` scripts for Kytos version 2025.0

This folder contains Topology's related scripts that should be run on kytos console:

<details>

<summary>

## Retire vlans from `interface.tag_ranges`

</summary>

Certain vlans may be reserved by the network interfaces,
making them unavailable for usage with kytos. This script ['001_retire_vlans.py'](./001_retire_vlans.py),
can be used to retire these vlans from use for all interfaces in the network.

This script temporarily disables all EVCs using the vlans to be retired,
then tries to retire the vlan from each interfaces,
and finally re-enables all the temporarily disabled EVCs.

### Disclaimer

If the vlans are still in use on an interface, even after disabling all the relevant EVCs, then the script will not retire the vlans on that interface, and will instead produce a warning message.

### How to use

- Change `DRY_RUN` to `False` for the script to make changes.
- Change `RETIRED_VLANS` to the set of vlan ranges to be retired, which by default is `[[4095, 4095]]`.
- Copy all the lines and paste them inside kytos console.

### Output example

```
Checking EVCs for vlan usage...
EVC f66461330a1640 is using s_vlan [[1, 1]] which is pending retirement, WILL temporarily disable it...
EVC 7c52f632e86049 is using s_vlan [[2, 2]] which is pending retirement, WILL temporarily disable it...
EVC 44b2b9c4a56b4d is using s_vlan [[3, 3]] which is pending retirement, WILL temporarily disable it...
EVC 2c7043e90e5245 is using s_vlan [[4, 4]] which is pending retirement, WILL temporarily disable it...
EVC 5c2fe24535b04c is using s_vlan [[5, 5]] which is pending retirement, WILL temporarily disable it...
Disabling EVCs...
Clearing vlan from tag_ranges and available_tags
Re-enabling EVCs...
Finished!
```

</details>