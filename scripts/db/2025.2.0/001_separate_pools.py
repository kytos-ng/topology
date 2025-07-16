#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import datetime
import os
from collections import defaultdict
from kytos.core.db import Mongo

from kytos.core.tag_ranges import range_addition, range_difference, range_intersection

OF_LLDP_TAG = ("vlan", 3799)

def gather_changes(mongo: Mongo):
    """Update database"""
    db = mongo.client[mongo.db_name]
    links = db.links.find()
    iface_details = db.interface_details.find()
    iface_details_by_iface = {
        iface_detail["id"]: iface_detail
        for iface_detail in iface_details
    }
    print(iface_details_by_iface)

    evc_documents = db.evcs.find({"archived": False})

    used_interface_tags = defaultdict(list)
    used_link_tags = defaultdict(list)

    link_tag_assignments = dict()
    interface_tag_assignments = dict()


    for evc in evc_documents:
        for uni in (evc["uni_a"], evc["uni_z"]):
            interface_id = uni["interface_id"]
            uni_tag = uni.get("tag")
            if uni_tag:
                used_interface_tags[interface_id].append(
                    (uni_tag["tag_type"], uni_tag["value"])
                )

        for path in (evc["current_path"], evc["failover_path"]):
            for link in path:
                link_id = link["id"]
                link_metadata = link["metadata"]
                s_vlan = link_metadata["s_vlan"]
                used_link_tags[link_id].append(
                    (s_vlan["tag_type"], s_vlan["value"])
                )

    for link in links:
        link_id = link["id"]

        used_link_tag_ranges = defaultdict(list)
        used_link_special_tags = defaultdict(set)

        for tag_type, tag_value in used_link_tags[link_id]:
            if isinstance(tag_value, str):
                used_link_special_tags[tag_type].add(tag_value)
            if isinstance(tag_value, int):
                used_link_tag_ranges[tag_type], _ = range_addition(
                    used_link_tag_ranges[tag_type],
                    [[tag_value, tag_value]]
                )
            if isinstance(tag_value, list):
                used_link_tag_ranges[tag_type], _ = range_addition(
                    used_link_tag_ranges[tag_type],
                    tag_value
                )

        relevant_endpoints = set()

        for endpoint in link["endpoints"]:
            relevant_endpoints.add(endpoint["id"])

        exclude_tag_ranges = defaultdict(list)
        exclude_special_tags = defaultdict(set)

        shared_tag_ranges = None
        shared_special_tags = None

        for endpoint_id in relevant_endpoints:
            for tag_type, tag_value in [
                *used_interface_tags[endpoint_id],
                OF_LLDP_TAG
            ]:
                if isinstance(tag_value, str):
                    exclude_special_tags[tag_type].add(tag_value)
                if isinstance(tag_value, int):
                    exclude_tag_ranges[tag_type], _ = range_addition(
                        exclude_tag_ranges[tag_type],
                        [[tag_value, tag_value]]
                    )
                if isinstance(tag_value, list):
                    exclude_tag_ranges[tag_type], _ = range_addition(
                        exclude_tag_ranges[tag_type],
                        tag_value
                    )
            endpoint_details = iface_details_by_iface[endpoint_id]
            if shared_tag_ranges is None:
                shared_tag_ranges = endpoint_details["tag_ranges"]
                shared_special_tags = endpoint_details["special_tags"]
                continue

            endpoint_tag_ranges = endpoint_details["tag_ranges"]
            endpoint_special_tags = endpoint_details["special_tags"]

            for tag_type in list(shared_tag_ranges):
                if tag_type not in endpoint_tag_ranges:
                    del shared_tag_ranges[tag_type]
                    del shared_special_tags[tag_type]
                    continue
                shared_tag_ranges[tag_type] = list(
                    range_intersection(
                        shared_tag_ranges[tag_type],
                        endpoint_tag_ranges[tag_type]
                    )
                )
                shared_special_tags[tag_type] = list(
                    set(shared_special_tags[tag_type]) &
                    set(endpoint_special_tags[tag_type])
                )
                if (
                    not shared_tag_ranges[tag_type] and
                    not shared_special_tags[tag_type]
                ):
                    del shared_tag_ranges[tag_type]
                    del shared_special_tags[tag_type]
                    continue

        link_tag_ranges = dict()
        link_special_tags = dict()

        link_available_tags = dict()
        link_special_available_tags = dict()

        for tag_type in list(shared_tag_ranges):
            link_tag_ranges[tag_type] = range_difference(
                shared_tag_ranges[tag_type],
                exclude_tag_ranges[tag_type]
            )
            link_special_tags[tag_type] = list(
                set(shared_special_tags[tag_type]) -
                exclude_special_tags[tag_type]
            )

            link_available_tags[tag_type] = range_difference(
                link_tag_ranges[tag_type],
                used_link_tag_ranges[tag_type]
            )

            link_special_available_tags[tag_type] = list(
                set(link_special_tags[tag_type]) - 
                used_link_special_tags[tag_type]
            )
        
        link_tag_assignments[link_id] = {
            "available_tags": link_available_tags,
            "tag_ranges": link_tag_ranges,
            "default_tag_ranges": link_tag_ranges,
            "special_available_tags": link_special_available_tags,
            "special_tags": link_special_tags,
            "default_special_tags": link_special_tags,
        }

        for endpoint in relevant_endpoints:
            endpoint_details = iface_details_by_iface[endpoint]
            endpoint_assignments = {
                "available_tags": {},
                "tag_ranges": {},
                "default_tag_ranges": {},
                "special_available_tags": {},
                "special_tags": {},
                "default_special_tags": {},
            }
            for tag_type in endpoint_details["tag_ranges"]:
                if tag_type in link_tag_ranges:
                    endpoint_assignments["available_tags"][tag_type] = range_difference(
                        endpoint_details["available_tags"][tag_type],
                        link_available_tags[tag_type]
                    )
                    endpoint_assignments["tag_ranges"][tag_type] = range_difference(
                        endpoint_details["tag_ranges"][tag_type],
                        link_tag_ranges[tag_type]
                    )
                    
                    endpoint_assignments["special_available_tags"][tag_type] = list(
                        set(endpoint_details["special_available_tags"][tag_type]) -
                        set(link_special_available_tags[tag_type])
                    )
                    endpoint_assignments["special_tags"][tag_type] = list(
                        set(endpoint_details["special_tags"][tag_type]) -
                        set(link_special_tags[tag_type])
                    )
                else:
                    endpoint_assignments["available_tags"][tag_type] = endpoint_details["available_tags"][tag_type]
                    endpoint_assignments["tag_ranges"][tag_type] = endpoint_details["tag_ranges"][tag_type]
                    
                    endpoint_assignments["special_available_tags"][tag_type] = endpoint_details["special_available_tags"][tag_type]
                    endpoint_assignments["special_tags"][tag_type] = endpoint_details["special_tags"][tag_type]

                endpoint_assignments["default_tag_ranges"][tag_type] = endpoint_assignments["tag_ranges"][tag_type]
                endpoint_assignments["default_special_tags"][tag_type] = endpoint_assignments["special_tags"][tag_type]

            interface_tag_assignments[endpoint] = endpoint_assignments

    unprocessed_endpoints = set(iface_details_by_iface) - set(interface_tag_assignments)

    print(unprocessed_endpoints)

    for endpoint in unprocessed_endpoints:
        endpoint_details = iface_details_by_iface[endpoint]
        endpoint_assignments = {
            "available_tags": {},
            "tag_ranges": {},
            "default_tag_ranges": {},
            "special_available_tags": {},
            "special_tags": {},
            "default_special_tags": {},
        }

        for tag_type in endpoint_details["tag_ranges"]:
            endpoint_assignments["available_tags"][tag_type] = endpoint_details["available_tags"][tag_type]
            endpoint_assignments["tag_ranges"][tag_type] = endpoint_details["tag_ranges"][tag_type]
            
            endpoint_assignments["special_available_tags"][tag_type] = endpoint_details["special_available_tags"][tag_type]
            endpoint_assignments["special_tags"][tag_type] = endpoint_details["special_tags"][tag_type]

            endpoint_assignments["default_tag_ranges"][tag_type] = endpoint_assignments["tag_ranges"][tag_type]
            endpoint_assignments["default_special_tags"][tag_type] = endpoint_assignments["special_tags"][tag_type]

        interface_tag_assignments[endpoint] = endpoint_assignments

    return interface_tag_assignments, link_tag_assignments

def modify_documents(
    mongo: Mongo,
    interface_tag_assignments: dict,
    link_tag_assignments: dict,
):
    db = mongo.client[mongo.db_name]

    modified_intfs = 0
    modified_links = 0

    now = datetime.datetime.utcnow()

    for endpoint_id, assignments in interface_tag_assignments.items():
        result = db.interface_details.update_one(
            {"_id": endpoint_id},
            {
                "$set": {
                    **assignments,
                    "updated_at": now,
                },
            }
        )
        modified_intfs += result.modified_count

    
    for endpoint_id, assignments in link_tag_assignments.items():
        result = db.link_details.update_one(
            {"_id": endpoint_id},
            {
                "$setOnInsert": {
                    "_id": endpoint_id,
                    "id": endpoint_id,
                    "inserted_at": now
                },
                "$set": {
                    **assignments,
                    "updated_at": now,
                },
            },
            upsert=True
        )
        modified_links += result.modified_count

    print(f"{modified_intfs} interface_details documents modified.")
    print(f"{modified_links} link_details documents inserted")

def migrate_to_separate_tag_pools(mongo: Mongo):
    modify_documents(mongo, *gather_changes(mongo))


def dry_run(mongo: Mongo):
    iface_docs, link_docs = gather_changes(mongo)
    print(f"Expected interface_details changes: {iface_docs}")
    print()
    print(f"Expected link_details changes: {link_docs}")

if __name__ == "__main__":
    mongo = Mongo()
    cmds = {
        "update_database": migrate_to_separate_tag_pools,
        "dry_run": dry_run,
    }
    try:
        cmd = os.environ["CMD"]
        selected_cmd = cmds[cmd]
    except KeyError:
        print(
            f"Please set the 'CMD' env var. \nIt has to be one of these: {list(cmds.keys())}"
        )
        sys.exit(1)
    selected_cmd(mongo)
