#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
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
                "default_tag_ranges": 1,
                "default_special_tags": 1,
            }}
        ]
    )
    for document in result:
        if (
            not "default_tag_ranges" in document or
            not "default_special_tags" in document
        ):
            outdated_intfs.add(document["id"])
    
    if outdated_intfs:
        print(f"There are {len(outdated_intfs)} outdated interface documents"
              " which do not have 'default_tag_ranges' and/or"
              " 'default_special_tags' field:")
        for intf_id in outdated_intfs:
            print(intf_id)
    else:
        print("All interfaces are updated.")

def update_database(mongo: Mongo):
    db = mongo.client[mongo.db_name]
    intfs_documents = db.interface_details.find()

    intf_count = 0
    message_intfs = ""
    for intf in intfs_documents:
        _id = intf["id"]
        if "default_tag_ranges" in intf and "default_special_tags" in intf:
            continue
        db.interface_details.update_one(
            {"id": _id},
            {
                "$set": {
                    "default_tag_ranges": {"vlan": [[1, 4094]]},
                    "default_special_tags": {"vlan": ["untagged", "any"]}
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
