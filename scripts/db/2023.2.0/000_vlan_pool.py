import datetime
import json
import sys
import os
from collections import defaultdict
from kytos.core.db import Mongo

DEFAULT_TAG_RANGES = [[1, 4095]]
custom_tag_range = json.loads(os.environ.get("CUSTOM_TAG_RANGE", "{}"))


def get_tag_range(intf_id) -> [list[list[int]]]:
    return custom_tag_range.get(intf_id, DEFAULT_TAG_RANGES)

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

def generate_ranges(avoid, intf_id) -> [list[list[int]]]:
    """Generate available_tags only from avoid"""
    if not avoid:
        return get_tag_range(intf_id)

    avoid.sort()
    ranges = []
    start = 1

    for num in avoid:
        if num > start:
            ranges.append([start, num - 1])
        start = num + 1

    if start <= 4095:
        ranges.append([start, 4095])
    return ranges

def update_database(mongo: Mongo):
    """Update database"""
    db = mongo.client[mongo.db_name]
    intf_documents = db.interface_details.find()
    evc_documents = db.evcs.find({"archived": False})

    evc_intf = defaultdict(str)
    evc_tags = defaultdict(set)

    for evc in evc_documents:
        tag_a = evc["uni_a"].get("tag")
        if tag_a:
            intf_id = evc["uni_a"]["interface_id"]
            if tag_a["value"] in evc_tags[intf_id] and isinstance(tag_a["value"], int):
                print(f"Error: Detected duplicated {tag_a['value']} TAG"
                      f" in EVCs {evc['id']} and {evc_intf[intf_id+str(tag_a['value'])]}"
                      f" in interface {intf_id}")
                sys.exit(1)
            evc_tags[intf_id].add(tag_a["value"])
            evc_intf[intf_id+str(tag_a["value"])] = evc["id"]

        tag_z = evc["uni_z"].get("tag")
        if tag_z:
            intf_id = evc["uni_z"]["interface_id"]
            if tag_z["value"] in evc_tags[intf_id] and isinstance(tag_z["value"], int):
                print(f"Error: Detected duplicated {tag_z['value']} TAG"
                      f" in EVCs {evc['id']} and {evc_intf[intf_id+str(tag_z['value'])]}"
                      f" in interface {intf_id}")
                sys.exit(1)
            evc_tags[intf_id].add(tag_z["value"])
            evc_intf[intf_id+str(tag_z["value"])] = evc["id"]

    intf_count = 0
    for document in intf_documents:
        avoid_tags = evc_tags.pop(document["id"], set())
        if document.get("available_vlans") is None:
            continue
        ranges = get_range(document["available_vlans"], avoid_tags)
        result = db.interface_details.update_one(
            {"id": document["id"]},
            {
                "$set":
                {
                    "available_tags": {"vlan": ranges},
                    "tag_ranges": {"vlan": get_tag_range(document["id"])}
                },
                "$unset": {"available_vlans": ""}
            }
        )
        intf_count += result.modified_count

    evc_intf_count = 0
    for intf_id, avoid_tags in evc_tags.items():
        available_tags = generate_ranges(list(avoid_tags), intf_id)
        utc_now = datetime.datetime.utcnow()
        result = db.interface_details.insert_one({
            "_id": intf_id,
            "id": intf_id,
            "inserted_at": utc_now,
            "updated_at": utc_now,
            "available_tags": {"vlan": available_tags},
            "tag_ranges": {"vlan": get_tag_range(intf_id)},
        })
        if result:
            evc_intf_count += 1

    print(f"{intf_count} documents modified. {evc_intf_count} documents inserted")

def aggregate_outdated_interfaces(mongo: Mongo):
    """Aggregate outdated inteface details"""
    db = mongo.client[mongo.db_name]
    document_ids = set()
    result = db.interface_details.aggregate(
        [
            {"$sort": {"_id": 1}},
            {"$project": {
                "_id": 0,
                "id": 1,
                "max_number": {"$max": "$available_vlans"}, # MAX deleted in 6.0
                "min_number": {"$min": "$available_vlans"}, # MIN deleted in 6.0
                "available_vlans": 1,
            }}
        ]
    )
    
    messages = ""
    for document in result:
        document_ids.add(document["id"])
        if document.get("available_vlans") is None:
            continue
        document.pop("available_vlans")
        messages += str(document) + "\n"

    if messages != "":
        print("Here are the outdated interfaces. 'available_vlans' have a massive"
          " amount of items, minimum and maximum items will be shown only")
        print(messages)
    
    evc_documents = db.evcs.find({"archived": False})
    evc_intf = defaultdict(str)
    evc_tags = defaultdict(set)

    for evc in evc_documents:
        tag_a = evc["uni_a"].get("tag")
        if tag_a:
            intf_id = evc["uni_a"]["interface_id"]
            if tag_a["value"] in evc_tags[intf_id] and isinstance(tag_a["value"], int):
                print(f"WARNING: Detected duplicated {tag_a['value']} TAG"
                      f" in EVCs {evc['id']} and {evc_intf[intf_id+str(tag_a['value'])]}"
                      f" in interface {intf_id}")
                print()
            evc_tags[intf_id].add(tag_a["value"])
            evc_intf[intf_id+str(tag_a["value"])] = evc["id"]

        tag_z = evc["uni_z"].get("tag")
        if tag_z:
            intf_id = evc["uni_z"]["interface_id"]
            if tag_z["value"] in evc_tags[intf_id] and isinstance(tag_z["value"], int):
                print(f"WARNING: Detected duplicated {tag_z['value']} TAG"
                      f" in EVCs {evc['id']} and {evc_intf[intf_id+str(tag_z['value'])]}"
                      f" in interface {intf_id}")
                print()
            evc_tags[intf_id].add(tag_z["value"])
            evc_intf[intf_id+str(tag_z["value"])] = evc["id"]

    for id_ in document_ids:
        evc_tags.pop(id_, None)

    if evc_tags:
        print("New documents are going to be created. From the next interfaces,"
              " these tags should be avoided")

    for intf, avoid_tags in evc_tags.items():
        if intf in document_ids:
            continue
        aux = {"id": intf, "avoid_tags": avoid_tags}
        print(aux)

    if not evc_tags and messages == "":
        print("There is nothing to update or add")


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
