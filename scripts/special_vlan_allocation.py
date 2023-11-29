import datetime
import sys
import os
from collections import defaultdict
from kytos.core.db import Mongo


def aggregate_outdated_interfaces(mongo: Mongo):
    """Aggregate outdated interfaces details"""
    db = mongo.client[mongo.db_name]
    outdated_intfs = set()
    result = db.interface_details.aggregate(
        [
            {"$project": {
                "_id": 0,
                "id": 1,
                "special_available_tags": 1,
            }}
        ]
    )
    for document in result:
        if (not "special_available_tags" in document or
                not "special_tags" in document):
            outdated_intfs.add(document["id"])
    
    if outdated_intfs:
        print(f"There are {len(outdated_intfs)} outdated interface documents"
              " which do not have 'special_available_tags' and/or"
              " 'special_tags' field:")
        for intf_id in outdated_intfs:
            print(intf_id)
    else:
        print("All interfaces are updated.")

def update_database(mongo: Mongo):
    db = mongo.client[mongo.db_name]
    intfs_documents = db.interface_details.find()
    evc_documents = db.evcs.find({"archived": False})

    tag_by_intf = defaultdict(set)
    evc_intf = defaultdict(str)

    for evc in evc_documents:
        tag_a = evc["uni_a"].get("tag")
        if tag_a and isinstance(tag_a["value"], str):
            intf_id = evc["uni_a"]["interface_id"]
            if tag_a["value"] in tag_by_intf[intf_id]:
                print(f"Error: Detected duplicated vlan '{tag_a['value']}' TAG"
                      f" in EVCs {evc['id']} and {evc_intf[intf_id+tag_a['value']]}"
                      f" in interface {intf_id}")
                sys.exit(1)
            tag_by_intf[intf_id].add(tag_a["value"])
            evc_intf[intf_id+tag_a["value"]] = evc["id"]
        tag_z = evc["uni_z"].get("tag")

        if tag_z and isinstance(tag_z["value"], str):
            intf_id = evc["uni_z"]["interface_id"]
            if tag_z["value"] in tag_by_intf[intf_id]:
                print(f"Error: Detected duplicated vlan '{tag_z['value']}' TAG"
                      f" in EVCs {evc['id']} and {evc_intf[intf_id+tag_z['value']]}"
                      f" in interface {intf_id}")
                sys.exit(1)
            tag_by_intf[intf_id].add(tag_z["value"])
            evc_intf[intf_id+tag_z["value"]] = evc["id"]

    default_special_vlans = {"untagged", "any"}
    intf_count = 0
    message_intfs = ""
    for intf in intfs_documents:
        _id = intf["id"]
        current_field = intf.get("special_available_tags", None)
        if current_field:
            current_field = set(current_field["vlan"])
        expected_field = default_special_vlans - tag_by_intf.get(_id, set())
        if current_field == expected_field and intf.get("special_tags"):
            continue
        db.interface_details.update_one(
            {"id": _id},
            {
                "$set":
                {
                    "special_available_tags": {"vlan": list(expected_field)},
                    "special_tags": {"vlan": ["untagged", "any"]}
                }
            }
        )
        message_intfs += f"{_id}\n"
        intf_count += 1
    if intf_count:
        print(f"{intf_count} interface was/were updated:")
        print(message_intfs)
    else:
        print("All interfaces are updated already.")


if __name__ == "__main__":
    mongo = Mongo()
    cmds = {
        "aggregate_outdated_interfaces": aggregate_outdated_interfaces,
        "update_database": update_database,
    }
    try:
        cmd = os.environ["CMD"]
        cmds[cmd](mongo)
    except KeyError:
        print(
            f"Please set the 'CMD' env var. \nIt has to be one of these: {list(cmds.keys())}"
        )
        sys.exit(1)
