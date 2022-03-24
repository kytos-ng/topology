"""TopoController."""
from typing import Optional

from datetime import datetime

from napps.kytos.topology.db.client import mongo_client
from napps.kytos.topology.db.client import bootstrap_index
from napps.kytos.topology.db.models import SwitchDoc
from napps.kytos.topology.db.models import LinkDoc

from kytos.core import log
import pymongo
from pymongo.collection import ReturnDocument


class TopoController:
    """TopoController."""

    def __init__(self, db_client=mongo_client, db_client_options=None) -> None:
        """Constructor of TopoController."""
        db_client_kwargs = db_client_options or {}
        self.db_client = db_client(**db_client_kwargs)
        self.db = self.db_client.napps

    def bootstrap_indexes(self) -> None:
        """Bootstrap all topology related indexes."""
        index_tuples = [
            ("switches", "interfaces.id", pymongo.ASCENDING),
            ("links", "endpoints.id", pymongo.ASCENDING),
            ("interface_vlan_tags", "interface_id", pymongo.ASCENDING),
        ]
        for collection, index, direction in index_tuples:
            if bootstrap_index(self.db, collection, index, direction):
                log.info(
                    f"Created DB index ({index}, {direction}), "
                    f"collection: {collection})"
                )

    def get_topology(self) -> dict:
        """Get topology from DB."""
        switches = self.get_switches()
        links = self.get_links()
        return {"topology": {**links, **switches}}

    def get_switches(self) -> dict:
        """Get switches from DB."""
        switches = self.db.switches.aggregate(
            [
                {"$sort": {"_id": 1}},
                {"$project": {"_id": 0}},
            ]
        )
        sws = {}
        for switch in switches:
            switch["interfaces"] = {
                value["id"]: value for value in switch.get("interfaces", [])
            }
            sws[switch["id"]] = switch
        return {"switches": sws}

    def get_links(self) -> dict:
        """Get links from DB."""
        links = self.db.links.aggregate(
            [
                {"$sort": {"_id": 1}},
                {
                    "$project": {
                        "_id": 0,
                        "id": 1,
                        "enabled": 1,
                        "active": 1,
                        "metadata": 1,
                        "endpoint_a": {"$first": "$endpoints"},
                        "endpoint_b": {"$last": "$endpoints"},
                    }
                },
            ]
        )
        return {"links": {value["id"]: value for value in links}}

    def get_interfaces(self) -> dict:
        """Get interfaces from DB."""
        interfaces = self.db.switches.aggregate(
            [
                {"$sort": {"_id": 1}},
                {"$project": {"interfaces": 1, "_id": 0}},
                {"$unwind": "$interfaces"},
                {"$replaceRoot": {"newRoot": "$interfaces"}},
            ]
        )
        return {"interfaces": {value["id"]: value for value in interfaces}}

    def _set_updated_at(self, update_expr: dict) -> None:
        """Set updated_at on $set expression."""
        if "$set" in update_expr:
            update_expr["$set"].update({"updated_at": datetime.utcnow()})
        else:
            update_expr.update({"$set": {"updated_at": datetime.utcnow()}})

    def _update_switch(self, dpid: str, update_expr: dict) -> Optional[dict]:
        """Try to find one switch and update it given an update expression."""
        self._set_updated_at(update_expr)
        return self.db.switches.find_one_and_update({"_id": dpid}, update_expr)

    def upsert_switch(self, dpid: str, switch_dict: dict) -> Optional[dict]:
        """Update or insert switch."""
        utc_now = datetime.utcnow()
        model = SwitchDoc(
            **{**switch_dict, **{"_id": dpid, "updated_at": utc_now}}
        )
        old_document = self.db.switches.find_one_and_update(
            {"_id": dpid},
            {
                "$set": model.dict(exclude={"inserted_at"}),
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.BEFORE,
            upsert=True,
        )
        return old_document

    def enable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and enable it."""
        return self._update_switch(dpid, {"$set": {"enabled": True}})

    def deactivate_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and deactivate it."""
        return self._update_switch(dpid, {"$set": {"active": False}})

    def disable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and disable it."""
        return self.db.switches._update_switch(
            dpid, {"$set": {"enabled": False, "interfaces.$[].enabled": False}}
        )

    def add_switch_metadata(self, dpid: str, metadata: dict) -> Optional[dict]:
        """Try to find a switch and add to its metadata."""
        update_expr = {"$set": {f"metadata.{k}": v for k, v in metadata.items()}}
        return self._update_switch(dpid, update_expr)

    def delete_switch_metadata_key(self, dpid: str, key: str) -> Optional[dict]:
        """Try to find a switch and delete a metadata key."""
        return self._update_switch(dpid, {"$unset": {f"metadata.{key}": ""}})

    def enable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to enable one interface and its embedded object on links."""
        return self._update_interface(interface_id, {"$set": {"enable": True}})

    def disable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to disable one interface and its embedded object on links."""
        return self._update_interface(interface_id, {"$set": {"enable": False}})

    def activate_interface(self, interface_id: str) -> Optional[dict]:
        """Try to activate one interface."""
        return self._update_interface(interface_id, {"$set": {"active": True}})

    def deactivate_interface(self, interface_id: str) -> Optional[dict]:
        """Try to deactivate one interface."""
        return self._update_interface(interface_id, {"$set": {"active": False}})

    def update_interface_link_id(
        self, interface_id: str, link_id: str
    ) -> Optional[dict]:
        """Try to update interface link_id."""
        return self._update_interface(
            interface_id, {"$set": {"link": link_id, "nni": True}}
        )

    def add_interface_metadata(
        self, interface_id: str, metadata: dict
    ) -> Optional[dict]:
        """Try to find an interface and add to its metadata."""
        update_expr = {"$set": {f"metadata.{k}": v for k, v in metadata.items()}}
        return self._update_interface(interface_id, update_expr)

    def delete_interface_metadata_key(
        self, interface_id: str, key: str
    ) -> Optional[dict]:
        """Try to find an interface and delete a metadata key."""
        return self._update_interface(interface_id, {"$unset": {f"metadata.{key}": ""}})

    def _update_interface(self, interface_id: str, update_expr: dict) -> Optional[dict]:
        """Try to update one interface and its embedded object on links."""

        self._set_updated_at(update_expr)
        interfaces_expression = {}
        links_expression = {}

        for operator, values in update_expr.items():
            interfaces_expression[operator] = {
                f"interfaces.$.{k}": v for k, v in values.items()
            }
            links_expression[operator] = {
                f"endpoints.$.{k}": v for k, v in values.items()
            }

        # TODO transaction
        updated = self.db.switches.find_one_and_update(
            {"interfaces.id": interface_id},
            interfaces_expression,
            return_document=ReturnDocument.AFTER,
        )
        self.db.links.find_one_and_update(
            {"endpoints.id": interface_id},
            links_expression,
            return_document=ReturnDocument.AFTER,
        )
        return updated

    def upsert_link(self, link_id: str, link_dict: dict) -> dict:
        """Update or insert a Link."""
        utc_now = datetime.utcnow()
        model = LinkDoc(
            **{
                **link_dict,
                **{
                    "updated_at": utc_now,
                    "_id": link_id,
                    "endpoints": [
                        link_dict.get("endpoint_a"),
                        link_dict.get("endpoint_b"),
                    ],
                },
            }
        )
        updated = self.db.links.find_one_and_update(
            {"_id": link_id},
            {
                "$set": model.dict(exclude={"inserted_at"}),
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.AFTER,
            upsert=True,
        )
        return updated

    def _update_link(self, link_id: str, update_expr: dict) -> Optional[dict]:
        """Try to find one link and update it given an update expression."""
        self._set_updated_at(update_expr)
        return self.db.links.find_one_and_update({"_id": link_id}, update_expr)

    def activate_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and activate it."""
        return self._update_link(link_id, {"$set": {"active": True}})

    def deactivate_link(self, link_id: str, interface_id: str) -> Optional[dict]:
        """Try to find one link and deactivate it."""
        return self._update_link(link_id, {"$set": {"active": False}})

    def enable_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and enable it."""
        return self._update_link(link_id, {"$set": {"enabled": True}})

    def disable_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and disable it."""
        return self._update_link(link_id, {"$set": {"enabled": False}})

    def add_link_metadata(self, link_id: str, metadata: dict) -> Optional[dict]:
        """Try to find link and add to its metadata."""
        update_expr = {"$set": {f"metadata.{k}": v for k, v in metadata.items()}}
        return self._update_link(link_id, update_expr)
