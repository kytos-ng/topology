#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import glob
import pickle
import os
import sys
from typing import Any, List, Tuple
from napps.kytos.topology.controllers import TopoController
from concurrent.futures import ThreadPoolExecutor, as_completed

topo_controller = TopoController()


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
    """Load topology status."""
    namespace = "kytos.topology.status"
    content = load_boxes_data(namespace)
    if namespace not in content:
        return ([], [])

    content = content[namespace]
    if "network_status" not in content:
        return ([], [])
    if "switches" not in content["network_status"]:
        return ([], [])

    links_status = content["network_status"].get("links", {})

    switches = []
    for switch in content["network_status"]["switches"].values():
        switch["_id"] = switch["id"]
        switches.append(switch)

    links = []
    for link_values in links_status.values():
        if "id" in link_values:
            link_values["_id"] = link_values["id"]
            links.append(link_values)

    return (switches, links)


def insert_from_topology_status(
    topo_controller=topo_controller,
) -> Tuple[List[dict], List[dict]]:
    """Insert from topology status."""
    loaded_switches, loaded_links = load_topology_status()

    insert_switches = []
    with ThreadPoolExecutor(max_workers=len(loaded_switches)) as executor:
        futures = [
            executor.submit(topo_controller.upsert_switch, switch["id"], switch)
            for switch in loaded_switches
        ]
        for future in as_completed(futures):
            response = future.result()
            insert_switches.append(response)

    insert_links = []
    with ThreadPoolExecutor(max_workers=len(loaded_links)) as executor:
        futures = [
            executor.submit(topo_controller.upsert_link, link["id"], link)
            for link in loaded_links
        ]
        for future in as_completed(futures):
            response = future.result()
            insert_switches.append(response)

    return (insert_switches, insert_links)


def load_topology_metadata(entity: str) -> dict:
    """Load topology metadata."""
    namespace = f"kytos.topology.{entity}.metadata"
    content = load_boxes_data(namespace)
    if namespace not in content:
        return {}
    content = content[namespace]
    return content


def insert_from_topology_switches_metadata(
    topo_controller=topo_controller,
) -> List[dict]:
    """Insert from topology switches metadata namespace."""
    switches = load_topology_metadata("switches")
    responses = []
    with ThreadPoolExecutor(max_workers=len(switches)) as executor:
        futures = [
            executor.submit(topo_controller.add_switch_metadata, dpid, metadata)
            for dpid, metadata in switches.items()
        ]
        for future in as_completed(futures):
            response = future.result()
            responses.append(response)
    return responses


def insert_from_topology_interfaces_metadata(
    topo_controller=topo_controller,
) -> List[dict]:
    """Insert from topology interfaces metadata namespace."""
    interfaces = load_topology_metadata("interfaces")
    responses = []
    with ThreadPoolExecutor(max_workers=len(interfaces)) as executor:
        futures = [
            executor.submit(
                topo_controller.add_interface_metadata, interface_id, metadata
            )
            for interface_id, metadata in interfaces.items()
        ]
        for future in as_completed(futures):
            response = future.result()
            responses.append(response)
    return responses


def insert_from_topology_links_metadata(topo_controller=topo_controller) -> List[dict]:
    """Insert from topology links metadata namespace."""
    links = load_topology_metadata("links")
    responses = []
    with ThreadPoolExecutor(max_workers=len(links)) as executor:
        futures = [
            executor.submit(topo_controller.add_link_metadata, link_id, metadata)
            for link_id, metadata in links.items()
        ]
        for future in as_completed(futures):
            response = future.result()
            responses.append(response)
    return responses


if __name__ == "__main__":
    cmds = {
        "insert_links_metadata": insert_from_topology_links_metadata,
        "insert_switches_metadata": insert_from_topology_switches_metadata,
        "insert_interfaces_metadata": insert_from_topology_interfaces_metadata,
        "insert_topology": insert_from_topology_status,
        "load_topology": lambda: json.dumps(load_topology_status()),
        "load_switches_metadata": lambda: json.dumps(
            load_topology_metadata("switches")
        ),
        "load_interfaces_metadata": lambda: json.dumps(
            load_topology_metadata("interfaces")
        ),
        "load_links_metadata": lambda: json.dumps(load_topology_metadata("links")),
    }
    try:
        cmd = os.environ["CMD"]
    except KeyError:
        print("Please set the 'CMD' env var.")
        sys.exit(1)
    try:
        for command in cmd.split(","):
            print(cmds[command]())
    except KeyError as e:
        print(
            f"Unknown cmd: {str(e)}. 'CMD' env var has to be one of these {list(cmds.keys())}."
        )
        sys.exit(1)
