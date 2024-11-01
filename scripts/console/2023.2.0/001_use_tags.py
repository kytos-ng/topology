from collections import defaultdict

# Change to False so this script makes changes
DRY_RUN = True
# Modify with VLAN used in of_lldp
OF_LLDP_VLAN = 3799
REMOVE_LLDP_FLOWS = False

def get_cookie(dpid: str) -> int:
    """Return the cookie integer given a dpid."""
    COOKIE_PREFIX = 0xab
    return (0x0000FFFFFFFFFFFF & int(dpid.replace(":", ""), 16) | (COOKIE_PREFIX << 56))

def remove_flows(dpid: str, cookie: int) -> None:
    import httpx
    FLOW_MANAGER_URL = 'http://localhost:8181/api/kytos/flow_manager/v2'
    url = f"{FLOW_MANAGER_URL}/flows/{dpid}"
    data = {"flows": [{
        "cookie": cookie,
        "cookie_mask": int(0xFFFFFFFFFFFFFFFF),
    }], "force": True}
    res = httpx.request("DELETE", url, json=data, timeout=10)
    if res.is_server_error or res.status_code in {424, 404, 400}:
        print(f"Error deleting LLDP flows from Switch {dpid}: {res.text}")

mef_eline = controller.napps[("kytos", "mef_eline")]
of_lldp = controller.napps[('kytos', 'of_lldp')]
evcs = {
    evc_id: evc.as_dict()
    for evc_id, evc in mef_eline.circuits.items()
    if not evc.archived
}

in_use_tags = defaultdict(list)
for evc_id, evc in evcs.items():
    for link in evc["current_path"]:
        svlan = link["metadata"]["s_vlan"]["value"]
        intfa = link["endpoint_a"]["id"]
        intfb = link["endpoint_b"]["id"]
        in_use_tags[intfa].append((svlan, evc_id))
        in_use_tags[intfb].append((svlan, evc_id))
    for link in evc["failover_path"]:
        svlan = link["metadata"]["s_vlan"]["value"]
        intfa = link["endpoint_a"]["id"]
        intfb = link["endpoint_b"]["id"]
        in_use_tags[intfa].append((svlan, evc_id))
        in_use_tags[intfb].append((svlan, evc_id))

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
                in_use_tags[intf_id].append((tag, evc_id))
            elif isinstance(tag, list):
                for tag_item in tag:
                    if isinstance(tag_item, int):
                        in_use_tags[intf_id].append((tag_item, evc_id))
                    elif isinstance(tag_item, list) and len(tag_item) == 1:
                        in_use_tags[intf_id].append((tag_item[0], evc_id))
                    elif isinstance(tag_item, list) and len(tag_item) == 2:
                        for val in range(tag_item[0], tag_item[1]+1):
                            in_use_tags[intf_id].append((val, evc_id))

switch_rm_flows = {}
flow_manager = controller.napps[('kytos', 'flow_manager')]
for dpid in list(controller.switches.keys()):
    switch = controller.get_switch_by_dpid(dpid)
    of_lldp_cookie = get_cookie(dpid)
    switch_lldp_flow = flow_manager.flow_controller.get_flows_by_cookie_ranges(
        [dpid], [(of_lldp_cookie, of_lldp_cookie)]
    )
    of_lldp_flow_flag = bool(switch_lldp_flow[dpid])
    if not switch.is_enabled() and of_lldp_flow_flag:
        print(f"WARNING: Switch {dpid} is disabled and has LLDP flows.")
        if REMOVE_LLDP_FLOWS:
            switch_rm_flows[dpid] = of_lldp_cookie
    
    for intf_id, intf in switch.interfaces.copy().items():
        if OF_LLDP_VLAN and switch.is_enabled() and of_lldp_flow_flag:
            in_use_tags[intf_id].append((OF_LLDP_VLAN, "of_lldp"))
        for tag, evc_id in in_use_tags[intf_id]:
            if intf.is_tag_available(tag, tag_type="vlan"):
                dry_run_key = "WILL" if not DRY_RUN else "WOULD"
                print(
                    f"s_vlan {tag} that was in use from EVC {evc_id} is still available on intf {intf_id}, {dry_run_key} use it..."
                )
                if not DRY_RUN:
                    intf.use_tags(controller, tag)

if REMOVE_LLDP_FLOWS and switch_rm_flows and not DRY_RUN:
    print("Deleting LLDP flows...")
    for dpid, cookie in switch_rm_flows.items():
        remove_flows(dpid, cookie)
