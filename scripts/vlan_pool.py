import datetime
from collections import defaultdict
from kytos.core.db import mongo_client

DEFAULT_TAG_RANGES = [[1, 4095]]

def get_range(vlans, avoid) -> list[list[int]]:
    """Convert available_vlans to available_tags.
    From list[int] to list[list[int]]"""
    result = []
    if not vlans:
        return result

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

def generate_ranges(avoid):
    if not avoid:
        return DEFAULT_TAG_RANGES

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

client = mongo_client()
intf_collection = client["napps"]["interface_details"]
evc_collection = client["napps"]["evcs"]
intf_documents = intf_collection.find()
evc_documents = evc_collection.find()

evc_intf_dict = defaultdict(set)

for evc in evc_documents:
    tag_a = evc["uni_a"].get("tag")
    if tag_a:
        intf_id = evc["uni_a"]["interface_id"]
        evc_intf_dict[intf_id].add(tag_a["value"])

    tag_z = evc["uni_z"].get("tag")
    if tag_z:
        intf_id = evc["uni_z"]["interface_id"]
        evc_intf_dict[intf_id].add(tag_z["value"])

for document in intf_documents:
    if document.get("available_vlans") is None:
        continue
    avoid_tags = evc_intf_dict.pop(document["id"], set())
    ranges = get_range(document["available_vlans"], avoid_tags)
    intf_collection.update_one(
        {"id": document["id"]},
        {
            "$set": 
            {
                "available_tags": {"vlan": ranges},
                "tag_ranges": {"vlan": DEFAULT_TAG_RANGES}
            },
            "$unset": {"available_vlans": ""}
        }
    )

for intf_id, avoid_tags in evc_intf_dict.items():
    available_tags = generate_ranges(list(avoid_tags))
    utc_now = datetime.datetime.utcnow()
    intf_collection.insert_one({
        "_id": intf_id,
        "id": intf_id,
        "inserted_at": utc_now,
        "updated_at": utc_now,
        "available_tags": {"vlan": available_tags},
        "tag_ranges": {"vlan": DEFAULT_TAG_RANGES},
    })

print("Finnished adding available_tags and tag_ranges")