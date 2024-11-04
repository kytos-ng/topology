from collections import defaultdict
from kytos.core.tag_ranges import range_difference

# Change to False so this script makes changes
DRY_RUN = True
# Modify with VLAN used in of_lldp
OF_LLDP_VLAN = 3799
# Change to False to not print the missing VLANs
PRINT_MISSING = True

def get_cookie(dpid: str) -> int:
    """Return the cookie integer given a dpid."""
    COOKIE_PREFIX = 0xab
    return (0x0000FFFFFFFFFFFF & int(dpid.replace(":", ""), 16) | (COOKIE_PREFIX << 56))

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
            and evc[uni]["tag"]
            and "tag_type" in evc[uni]["tag"]
            and evc[uni]["tag"]["tag_type"] in ("vlan", 1)
        ):
            tag = evc[uni]["tag"]["value"]
            if isinstance(tag, int):
                in_use_tags[intf_id].add(tag)
            elif isinstance(tag, list):
                for tag_item in tag:
                    if isinstance(tag_item, int):
                        in_use_tags[intf_id].add(tag_item)
                    elif isinstance(tag_item, list) and len(tag_item) == 1:
                        in_use_tags[intf_id].add(tag_item[0])
                    elif isinstance(tag_item, list) and len(tag_item) == 2:
                        for val in range(tag_item[0], tag_item[1]+1):
                            in_use_tags[intf_id].add(val)

switch_rm_flows = {}
flow_manager = controller.napps[('kytos', 'flow_manager')]
for dpid in list(controller.switches.keys()):
    switch = controller.get_switch_by_dpid(dpid)
    of_lldp_cookie = get_cookie(switch.id)
    switch_lldp_flow = flow_manager.flow_controller.get_flows_by_cookie_ranges(
        [dpid], [(of_lldp_cookie, of_lldp_cookie)]
    )
    of_lldp_flow_flag = bool(switch_lldp_flow[dpid])

    for interface in switch.interfaces.copy().values():
        intf_id = interface.id
        vlans = in_use_tags.get(intf_id, set())
        if OF_LLDP_VLAN and switch.is_enabled() and of_lldp_flow_flag:
            vlans.add(OF_LLDP_VLAN)
        vlans = get_range(sorted(list(vlans)), set())
        intf = controller.get_interface_by_id(intf_id)
        tag_range = intf.tag_ranges["vlan"]
        available_tags = range_difference(tag_range, vlans)
        if intf.available_tags["vlan"] != available_tags:
            print(f"Inconsistent available tags in interface {intf_id}:\n"
                  f"WRONG -> {intf.available_tags['vlan']}\n"
                  f"CORRECT -> {available_tags}")
            if PRINT_MISSING:
                print(f"AVAILABLE MISSING -> {range_difference(available_tags, intf.available_tags['vlan'])}")
            if not DRY_RUN:
                intf.make_tags_available(controller, available_tags, 'vlan')
            print("\n")
