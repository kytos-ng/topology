"""TopoController."""
from typing import Optional

from datetime import datetime

from napps.kytos.topology.db.client import mongo_client
from napps.kytos.topology.db.client import bootstrap_index
from napps.kytos.topology.db.models.switch import SwitchModel
from napps.kytos.topology.db.models.link import LinkModel
from kytos.core import log
import pymongo
from pymongo.collection import ReturnDocument
from pydantic import ValidationError

# TODO add api models


class TopoController:
    """TopoController."""

    def __init__(self, db_client=mongo_client, db_client_options=None) -> None:
        """Constructor of TopoController."""
        db_client_kwargs = db_client_options or {}
        self.db_client = db_client(**db_client_kwargs)
        self.db = self.db_client.napps

    def bootstrap_indexes(self) -> None:
        """Bootstrap all topology related indexes."""
        index_tuples = [("switches", "interfaces.id", pymongo.ASCENDING)]
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
        return {**links, **switches}

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
                {"$project": {"_id": 0}},
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

    def _update_switch(self, dpid: str, items_dict: dict) -> Optional[dict]:
        """Try to find one switch and update it."""
        items_dict["updated_at"] = datetime.utcnow()
        return self.db.switches.find_one_and_update({"_id": dpid}, {"$set": items_dict})

    def upsert_switch(self, dpid: str, switch_dict: dict) -> dict:
        """Update or insert switch."""
        try:
            utc_now = datetime.utcnow()
            model = SwitchModel(**{**switch_dict, **{"updated_at": utc_now}})
            updated = self.db.switches.find_one_and_update(
                {"_id": dpid},
                {
                    "$set": model.dict(exclude={"inserted_at"}),
                    "$setOnInsert": {"inserted_at": utc_now},
                },
                return_document=ReturnDocument.AFTER,
                upsert=True,
            )
            return updated
        except ValidationError as err:
            raise err

    def enable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and enable it."""
        return self._update_switch(dpid, {"enabled": True})

    def deactivate_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and deactivate it."""
        return self._update_switch(dpid, {"active": False})

    def disable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and disable it."""
        return self.db.switches._update_switch(
            dpid, {"enabled": False, "interfaces.$[].enabled": False}
        )

    def update_switch_metadata(self, dpid: str, metadata: dict) -> Optional[dict]:
        """Try to one switch and update its metadata."""
        return self._update_switch(dpid, {"metadata": metadata})

    def enable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to enable one interface."""
        return self.db.switches.find_one_and_update(
            {"interfaces.id": interface_id}, {"$set": {"interfaces.$.enabled": True}}
        )

    def disable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to disable one interface."""
        return self._update_interface(interface_id, {"enable": False})

    def disable_interface_link(self, interface_id: str) -> Optional[dict]:
        """Try to disable one interface and its link."""
        # TODO wrap this in a transation, make sure replica set is all set
        updated = self.disable_interface(interface_id)
        self.disable_link(updated.get("link", ""))
        return updated

    def activate_interface(self, interface_id: str) -> Optional[dict]:
        """Try to activate one interface."""
        return self._update_interface(interface_id, {"active": True})

    def deactivate_interface(self, interface_id: str) -> Optional[dict]:
        """Try to deactivate one interface."""
        return self._update_interface(interface_id, {"active": False})

    def update_interface_link_id(
        self, interface_id: str, link_id: str
    ) -> Optional[dict]:
        """Try to update interface link_id."""
        return self._update_interface(
            interface_id, {"link": link_id, "nni": True, "uni": False}
        )

    def _update_interface(self, interface_id: str, items_dict: dict) -> Optional[dict]:
        """Try to find one interface and update it."""
        items_dict = {f"interfaces.$.{k}": v for k, v in items_dict.items()}
        updated = self.db.switches.find_one_and_update(
            {"interfaces.id": interface_id},
            {"$set": items_dict},
            return_document=ReturnDocument.AFTER,
        )
        return updated

    def upsert_link(self, link_id: str, link_dict: dict) -> dict:
        """Update or insert a Link."""
        try:
            utc_now = datetime.utcnow()
            model = LinkModel(
                **{**link_dict, **{"updated_at": utc_now, "_id": link_id}}
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
        except ValidationError as err:
            raise err

    def _update_link(self, link_id: str, items_dict: dict) -> Optional[dict]:
        """Try to find one link and update it."""
        items_dict["updated_at"] = datetime.utcnow()
        return self.db.links.find_one_and_update({"_id": link_id}, {"$set": items_dict})

    def activate_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and activate it."""
        return self._update_link(link_id, {"active": True})

    def deactivate_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and deactivate it."""
        return self._update_link(link_id, {"active": False})

    def enable_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and enable it."""
        return self._update_link(link_id, {"enabled": True})

    def disable_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and disable it."""
        return self._update_link(link_id, {"enabled": False})

    def add_link_metadata(self, link_id: str, metadata: dict) -> Optional[dict]:
        """Try to find link and add to its metadata."""
        metadata_items = {f"metadata.{k}": v for k, v in metadata.items()}
        return self._update_link(link_id, metadata_items)
