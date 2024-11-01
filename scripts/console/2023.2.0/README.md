## `topology` scripts for Kytos version 2023.2.0

This folder contains Topology's related scripts that should be run on kytos console:

<details><summary><h3>Use VLANs in <code>interface.available_vlans</code></h3></summary>

Some paths were not dealocating VLANs from their respective interfaces. This script [`001_use_tags.py`](./001_use_tags.py) identifies them and allocates them. This script will also try to remove LLDP flows in disabled switches if ``REMOVE_LLDP_FLOWS`` is ``True``.

### How to use

- Change ``DRY_RUN`` to ``False`` for the script to make changes.
- Change ``OF_LLDP_VLAN`` to the correct VLAN that ``of_lldp`` uses which by default is 3799.
- Change ``REMOVE_LLDP_FLOWS`` to ``True`` so the script tries to remove the LLDP flows from disabled switches.
- Copy all the lines and paste them inside kytos console.

### Output example

```
WARNING: Switch 00:00:00:00:00:00:00:01 is disabled and has LLDP flows.
s_vlan 2 that was in use from EVC c6156083ae514e is still available on intf 00:00:00:00:00:00:00:04:2, WOULD use it...
Deleting LLDP flows...
```

</details>

<details><summary><h3>Recover missing VLANs in <code>interface.available_vlans</code></h3></summary>

After the migration to ranges of VLANs, if some VLANs are missing from ``interface.available_vlans`` use this the script [`002_recover_vlans.py`](./002_recover_vlans.py) in kytos console.

### Disclaimer

This script will also log inconsistencies in ``interface.available_vlans`` but it will only make VLANs available and it will not use vlans.

### How to use

- Change ``DRY_RUN`` to ``False`` for the script to make changes. Otherwise it will only print out the incorrect and correct ``available_tags`` in each interface. 
- Change ``OF_LLDP_VLAN`` to the correct VLAN that ``of_lldp`` uses which by default is 3799.
- Change ``PRINT_MISSING`` to ``False`` so missing VLANs ranges are not printed. Changing to False will help with performance.
- Copy all the lines and paste them inside kytos console.

### Output example

```
Inconsistent available tags in interface 00:00:00:00:00:00:00:02:3:
WRONG -> [[1, 4095]]
CORRECT -> [[1, 3798], [3800, 4095]]
AVAILABLE MISSING -> []
```

</details>