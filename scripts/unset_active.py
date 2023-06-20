#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

from kytos.core.db import Mongo


def unset_links(mongo: Mongo) -> None:
    """Unset links"""
    print(
        "Trying to $unset links 'active' and metadata[last_status_is_active|last_status_change|notified_up_at]..."
    )
    db = mongo.client[mongo.db_name]
    res = db.links.update_many(
        {},
        {
            "$unset": {
                "active": 1,
                "metadata.last_status_is_active": 1,
                "metadata.last_status_change": 1,
                "metadata.notified_up_at": 1,
            }
        },
    )
    print(f"Modified {res.modified_count} links objects")


def aggregate_unset_links(mongo: Mongo) -> None:
    """Aggregate unset links."""
    db = mongo.client[mongo.db_name]
    res = db.links.aggregate(
        [
            {
                "$unset": [
                    "active",
                    "metadata.last_status_is_active",
                    "metadata.last_status_change",
                    "metadata.notified_up_at",
                ]
            }
        ]
    )
    print(
        "Aggregating links $unset active and metadata[last_status_is_active|last_status_change|notified_up_at]"
    )
    for doc in res:
        print(doc)


def unset_switches_and_intfs(mongo: Mongo) -> None:
    """Unset switches and interfaces"""
    print("Trying to $unset switches and interfaces 'active'")
    db = mongo.client[mongo.db_name]
    res = db.switches.update_many(
        {},
        {
            "$unset": {
                "active": 1,
                "interfaces.$[].active": 1,
            }
        },
    )
    print(f"Modified {res.modified_count} links objects")


def aggregate_unset_switches_and_intfs(mongo: Mongo) -> None:
    """Aggregate unset switches and interfaces."""
    db = mongo.client[mongo.db_name]
    res = db.switches.aggregate(
        [
            {
                "$unset": [
                    "active",
                    "interfaces.active",
                ]
            }
        ]
    )
    print(
        "Aggregating links $unset active and metadata[last_status_is_active|last_status_change|notified_up_at]"
    )
    for doc in res:
        print(doc)


if __name__ == "__main__":
    mongo = Mongo()
    cmds = {
        "aggregate_unset_links": aggregate_unset_links,
        "unset_links": unset_links,
        "aggregate_unset_switches_and_intfs": aggregate_unset_switches_and_intfs,
        "unset_switches_and_intfs": unset_switches_and_intfs,
    }
    try:
        cmd = os.environ["CMD"]
        cmds[cmd](mongo)
    except KeyError:
        print(
            f"Please set the 'CMD' env var. \nIt has to be one of these: {list(cmds.keys())}"
        )
        sys.exit(1)
