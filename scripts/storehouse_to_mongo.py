#!/usr/bin/env python
# -*- coding: utf-8 -*-

import glob
import pickle
import os
from typing import Any, List, Tuple
from napps.kytos.topology.db.models import SwitchDoc
from napps.kytos.topology.db.models import LinkDoc
from napps.kytos.topology.db.client import mongo_client

client = mongo_client()


def get_storehouse_dir() -> str:
    return os.environ["STOREHOUSE_NAMESPACES_DIR"]


def _list_boxes_files(namespace: str, storehouse_dir=get_storehouse_dir()) -> dict:
    """List boxes files given the storehouse dir."""
    if storehouse_dir.endswith(os.path.sep):
        storehouse_dir = storehouse_dir[:-1]
    return {
        file_name.split(os.path.sep)[-2]: file_name
        for file_name in glob.glob(f"{storehouse_dir}/{namespace}**/*", recursive=True)
    }


def _load_from_file(file_name) -> Any:
    with open(file_name, "rb") as load_file:
        return pickle.load(load_file)


def load_boxes_data(namespace: str) -> dict:
    """Load boxes data."""
    return {k: _load_from_file(v).data for k, v in _list_boxes_files(namespace).items()}


def load_topology_status() -> Tuple[List[dict], List[dict]]:
    """Map topology status."""
    namespace = "kytos.topology.status"
    content = load_boxes_data(namespace)
    if namespace not in content:
        return ([], [])

    content = content[namespace]
    if "network_status" not in content:
        return ([], [])
    if "switches" not in content["network_status"]:
        return ([], [])

    links = content["network_status"].get("links", {})

    switches = []
    for switch in content["network_status"]["switches"].values():
        switch["_id"] = switch["id"]
        if "interfaces" in switch:
            switch["interfaces"] = list(switch["interfaces"].values())
        switches.append(switch)

    for link_values in links.values():
        if "id" in link_values:
            link_values["_id"] = link_values["id"]

    return (
        [SwitchDoc(**switch).dict() for switch in switches],
        [LinkDoc(**link).dict() for link in links.values()],
    )


def insert_from_topology_status(client=client) -> Tuple[List[str], List[str]]:
    """Insert from topology status."""
    db = client.napps
    switches = db.switches

    loaded_switches, loaded_links = load_topology_status()
    listed_switches = list(
        switches.find(
            {
                "_id": {"$in": [switch["id"] for switch in loaded_switches]},
            },
            {"_id": 1},
        )
    )
    listed_ids = set([switch["_id"] for switch in listed_switches])

    insert_switches = []
    for switch in loaded_switches:
        if switch["id"] not in listed_ids:
            insert_switches.append(switch)
    if insert_switches:
        insert_switches = switches.insert_many(insert_switches).inserted_ids

    links = db.links
    listed_links = list(
        links.find({"_id": {"$in": [link["id"] for link in loaded_links]}}, {"_id": 1})
    )
    link_listed_ids = set([link["_id"] for link in listed_links])

    insert_links = []
    for link in loaded_links:
        if link["id"] not in link_listed_ids:
            insert_links.append(link)
    if insert_links:
        insert_links = links.insert_many(insert_links).inserted_ids

    return (insert_switches, insert_links)


if __name__ == "__main__":
    # print(json.dumps(load_topology_status()))
    # TODO break as a CLI
    print(insert_from_topology_status())
