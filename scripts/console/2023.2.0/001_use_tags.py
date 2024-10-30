from collections import defaultdict

DRY_RUN = True

mef_eline = controller.napps[("kytos", "mef_eline")]
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


for intf_id in in_use_tags:
    intf = controller.get_interface_by_id(intf_id)
    for tag, evc_id in in_use_tags[intf_id]:
        if intf.is_tag_available(tag, tag_type="vlan"):
            dry_run_key = "WILL" if not DRY_RUN else "WOULD"
            print(
                f"s_vlan {tag} that was in use from EVC {evc_id} is still available on intf {intf_id}, {dry_run_key} use it..."
            )
            if not DRY_RUN:
                intf.use_tags(controller, tag)