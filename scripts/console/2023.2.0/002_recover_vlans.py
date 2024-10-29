from collections import defaultdict
from kytos.core.tag_ranges import range_difference

# Change to False so this script makes changes
DRY_RUN = True
# Modify with VLAN used in of_lldp
OF_LLDP_VLAN = 3799
# Change to False to not print the missing VLANs
PRINT_MISSING = True

def get_range(vlans, avoid) -> list[list[int]]:
    """Convert available_vlans to available_tags.
    From list[int] to list[list[int]]"""
    result = []
    if not vlans:
        return result
    vlans.sort()
    i = 0
    while i < len(vlans):
        if vlans[i] in avoid:
            i += 1
        else:
            break
    if not vlans[i:]:
        return result

    start = end = vlans[i]
    for tag in vlans[i+1:]:
        if tag in avoid:
            continue
        if tag == end + 1:
            end = tag
        else:
            result.append([start, end])
            start = end = tag
    result.append([start, end])
    return result

mef_eline = controller.napps[('kytos', 'mef_eline')]
evcs = {evc_id: evc.as_dict() for evc_id, evc in mef_eline.circuits.items() if not evc.archived}
interfaces = {}
for dpid, switch in controller.switches.items():
    for intf_id, interface in switch.interfaces.items():
        interfaces[interface.id] = interface


in_use_tags = defaultdict(set)
for evc_id, evc in evcs.items():
    for link in evc["current_path"]:
        svlan = link["metadata"]["s_vlan"]["value"]
        intfa = link["endpoint_a"]["id"]
        intfb = link["endpoint_b"]["id"]
        in_use_tags[intfa].add(svlan)
        in_use_tags[intfb].add(svlan)
    for link in evc["failover_path"]:
        svlan = link["metadata"]["s_vlan"]["value"]
        intfa = link["endpoint_a"]["id"]
        intfb = link["endpoint_b"]["id"]
        in_use_tags[intfa].add(svlan)
        in_use_tags[intfb].add(svlan)
    for uni in ("uni_a", "uni_z"):
        intf_id = evc[uni]["interface_id"]
        if (
            "tag" in evc[uni]
            and "tag_type" in evc[uni]["tag"]
            and evc[uni]["tag"]["tag_type"] in ("vlan", 1)
        ):
            tag = evc[uni]["tag"]["value"]
            if isinstance(tag, int):
                in_use_tags[intf_id].add((tag, evc_id))
            elif isinstance(tag, list):
                for tag_item in tag:
                    if isinstance(tag_item, int):
                        in_use_tags[intf_id].add(tag_item)
                    elif isinstance(tag_item, list) and len(tag_item) == 1:
                        in_use_tags[intf_id].add(tag_item[0])
                    elif isinstance(tag_item, list) and len(tag_item) == 2:
                        for val in range(tag_item[0], tag_item[1]+1):
                            in_use_tags[intf_id].add(val)

for intf_id, interface in interfaces.items():
    vlans = in_use_tags.get(intf_id, set())
    if OF_LLDP_VLAN:
        vlans.add(OF_LLDP_VLAN)
    vlans = get_range(sorted(list(vlans)), set())
    intf = controller.get_interface_by_id(intf_id)
    tag_range = intf.tag_ranges["vlan"]
    available_tags = range_difference(tag_range, vlans)
    if intf.available_tags["vlan"] != available_tags:
        print(f"Missing available tags in interface {intf_id}:\n"
              f"WRONG -> {intf.available_tags['vlan']}\n"
              f"CORRECT -> {available_tags}")
        if PRINT_MISSING:
            print(f"MISSING -> {range_difference(available_tags, intf.available_tags['vlan'])}")
        print("\n")
        if not DRY_RUN:
            intf.make_tags_available(controller, available_tags, 'vlan')
