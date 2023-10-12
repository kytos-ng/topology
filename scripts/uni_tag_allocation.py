import os
import sys
import datetime
from kytos.core.db import Mongo
from collections import defaultdict

def update_database(mongo: Mongo):
    db = mongo.client[mongo.db_name]

    circuits = db.evcs.find({},
        {"uni_a": 1, "uni_z": 1}
    )
    intf_update = defaultdict(list)
    for circuit in circuits:
        tag_a = circuit["uni_a"].get("tag")
        tag_z = circuit["uni_z"].get("tag")
        if tag_a:
            intf_a = circuit["uni_a"]["interface_id"]
            intf_update[intf_a].append(tag_a["value"])
        if tag_z:
            intf_z = circuit["uni_z"]["interface_id"]
            intf_update[intf_z].append(tag_z["value"])

    modi_count = 0
    intf_details = db.interface_details.find()
    for document in intf_details:
        tag_list = intf_update.pop(document["id"], None)
        if not tag_list:
            continue
        result = db.interface_details.update_one(
            {"id": document["id"]},
            {"$pull": {"available_vlans": {"$in": tag_list}}}
        )
        modi_count += result.modified_count

    added_count = 0
    for intf_id, tag_list in intf_update.items():
        tag_list = set(tag_list)
        new_list = []
        for tag in range(1, 4096):
            if tag in tag_list:
                continue
            new_list.append(tag)
        utc_now = datetime.datetime.utcnow()
        result = db.interface_details.insert_one({
            "_id": intf_id,
            "id": intf_id,
            "inserted_at": utc_now,
            "updated_at": utc_now,
            "available_vlans": new_list,
        })
        added_count += 1
    
    print(f"{modi_count} documents modified. {added_count} documents inserted")

def aggregate_uni_tags(mongo: Mongo):
    db = mongo.client[mongo.db_name]

    circuits = db.evcs.find(
        {},
        {
            "uni_a": 1,
            "uni_z": 1
        }
    )
    intf_update = defaultdict(list)
    for circuit in circuits:
        tag_a = circuit["uni_a"].get("tag")
        tag_z = circuit["uni_z"].get("tag")
        if tag_a:
            intf_a = circuit["uni_a"]["interface_id"]
            intf_update[intf_a].append(tag_a["value"])
        if tag_z:
            intf_z = circuit["uni_z"]["interface_id"]
            intf_update[intf_z].append(tag_z["value"])

    if not intf_update:
        return

    print("Interfaces that probably need their available_vlans modified.")
    for intf in intf_update:
        print(f"{intf}: {intf_update[intf]}")

if __name__ == "__main__":
    mongo = Mongo()
    cmds = {
        "aggregate_uni_tags": aggregate_uni_tags,
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