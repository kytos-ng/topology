#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from functools import partial
import sys
import os

from kytos.core.db import Mongo
from pymongo.collection import Collection

def unset_collection_metadata(type: str, collection: Collection, metadata_fields: list[str]) -> None:
    """Unset switch or link metadata"""
    print(
        f"Trying to $unset {type} metadata[{'|'.join(metadata_fields)}]..."
    )
    db = mongo.client[mongo.db_name]
    res = collection.update_many(
        {},
        {
            "$unset": {
                f"metadata.{field}": 1
                for field in metadata_fields
            }
        },
    )
    print(f"Modified {res.modified_count} {type} objects")

def unset_interface_metadata(switches: Collection, metadata_fields: list[str]) -> None:
    """Unset interface metadata"""
    print(f"Trying to $unset interface metadata[{'|'.join(metadata_fields)}]...")
    res = switches.update_many(
        {},
        {
            "$unset": {
                f"interfaces.$[].metadata.{field}": 1
                for field in metadata_fields
            }
        },
    )
    print(f"Modified {res.modified_count} switches objects")



if __name__ == "__main__":
    mongo = Mongo()
    db = mongo.client[mongo.db_name]
    cmds = {
        "retire_link_metadata": partial(
            unset_collection_metadata,
            "link",
            db["links"]
        ),
        "retire_switch_metadata": partial(
            unset_collection_metadata,
            "switch",
            db["switches"]
        ),
        "retire_interface_metadata": partial(
            unset_interface_metadata,
            db["switches"]
        ),
    }
    try:
        cmd = os.environ["CMD"]
        command = cmds[cmd]
    except KeyError:
        print(
            f"Please set the 'CMD' env var. \nIt has to be one of these: {list(cmds.keys())}"
        )
        sys.exit(1)
    try:
        retire_metadata = os.environ["RETIRE_METADATA"].split(":")
    except KeyError:
        print(
            "Please set the 'RETIRE_METADATA' env var. \n"
            "It should be a ':' separated list of metadata variables to retire."
        )
        sys.exit(1)
        
    command(retire_metadata)
    
