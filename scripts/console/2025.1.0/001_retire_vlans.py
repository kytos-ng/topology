from collections import defaultdict
import concurrent.futures

import kytos.core.tag_ranges as range_helpers

# Change to False so this script makes changes
DRY_RUN = True
# Modify with VLAN ranges being retired from use
RETIRED_VLANS = [[1, 99]]

def disable_evc(evc_id):
    import httpx
    MEF_ELINE_URL = 'http://localhost:8181/api/kytos/mef_eline/v2'
    url = f"{MEF_ELINE_URL}/evc/{evc_id}"
    data = {
        "enabled": False
    }
    try:
        res = httpx.request("PATCH", url, json=data, timeout=30)
    except httpx.TimeoutException:
        print(f"Timeout while enabling EVC {evc_id}")
    if res.is_server_error or res.status_code in {424, 404, 400}:
        print(f"Error disabling EVC {evc_id}: {res.text}")

def enable_evc(evc_id):
    import httpx
    MEF_ELINE_URL = 'http://localhost:8181/api/kytos/mef_eline/v2'
    url = f"{MEF_ELINE_URL}/evc/{evc_id}"
    data = {
        "enabled": True
    }
    try:
        res = httpx.request("PATCH", url, json=data, timeout=30)
    except httpx.TimeoutException:
        print(f"Timeout while enabling EVC {evc_id}")
    if res.is_server_error or res.status_code in {424, 404, 400}:
        print(f"Error enabling EVC {evc_id}: {res.text}")

mef_eline = controller.napps[("kytos", "mef_eline")]
of_lldp = controller.napps[('kytos', 'of_lldp')]
topology = controller.napps[('kytos', 'topology')]

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

evc_disable_set = set()

dry_run_key = "WILL" if not DRY_RUN else "WOULD"

print("Checking EVCs for vlan usage...")

# Find all evcs to temporarily disable
for intf_id in in_use_tags:
    for tag, evc_id in in_use_tags[intf_id]:
        if evc_id in evc_disable_set:
            continue
        intersect = range_helpers.range_intersection([[tag, tag]], RETIRED_VLANS)
        intersect = list(intersect)
        if intersect:
            print(
                f"EVC {evc_id} is using s_vlan {intersect} which is pending retirement, {dry_run_key} temporarily disable it..."
            )
            evc_disable_set.add(evc_id)

# Disable EVCs
if not DRY_RUN and evc_disable_set:
    print("Disabling EVCs...")
    executor = concurrent.futures.ThreadPoolExecutor(10, "script:disable_evc")
    executor.map(disable_evc, evc_disable_set)
    executor.shutdown()

# Retire the given vlan ranges

if not DRY_RUN:
    print("Clearing vlan from tag_ranges and available_tags")
else:
    print("Checking interfaces for vlan usage...")

for dpid in list(controller.switches.keys()):
    switch = controller.get_switch_by_dpid(dpid)
    for intf_id, intf in switch.interfaces.copy().items():
        with intf.tag_lock:
            old_range = intf.tag_ranges['vlan']
            used_tags = range_helpers.range_difference(
                old_range, intf.available_tags['vlan']
            )
            new_range = range_helpers.range_difference(
                old_range, RETIRED_VLANS
            )
            missing = range_helpers.range_difference(
                used_tags, new_range
            )
            if missing:
                if not DRY_RUN:
                    print(
                        f"WARNING: Interface {dpid} {intf_id} still has the vlans {missing} in use. Can't retire vlans."
                    )
                else:
                    print(
                        f"Interface {dpid} {intf_id} has the vlans {missing} in use."
                    )
                continue
            change = range_helpers.range_difference(
                old_range, new_range
            )
            if not DRY_RUN and change:
                new_available_tags = range_helpers.range_difference(
                    new_range, used_tags
                )
                intf.available_tags['vlan'] = new_available_tags
                intf.tag_ranges['vlan'] = new_range
                topology.handle_on_interface_tags(intf)

# Re-enable the evcs

if not DRY_RUN and evc_disable_set:
    print("Re-enabling EVCs...")
    executor = concurrent.futures.ThreadPoolExecutor(10, "script:enable_evc")
    executor.map(enable_evc, evc_disable_set)
    executor.shutdown()

print("Finished!")
