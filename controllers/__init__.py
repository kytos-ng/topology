"""TopoController."""
from typing import List
from typing import Optional
from typing import Tuple
from threading import Lock

from datetime import datetime

from napps.kytos.topology.db.client import mongo_client
from napps.kytos.topology.db.client import bootstrap_index
from napps.kytos.topology.db.models import SwitchDoc
from napps.kytos.topology.db.models import LinkDoc
from napps.kytos.topology.db.models import InterfaceDetailDoc

from kytos.core import log
import pymongo
from pymongo.collection import ReturnDocument
from pymongo.operations import ReplaceOne
from pymongo.operations import UpdateOne


class TopoController:
    """TopoController."""

    def __init__(self, db_client=mongo_client, db_client_options=None) -> None:
        """Constructor of TopoController."""
        db_client_kwargs = db_client_options or {}
        self.db_client = db_client(**db_client_kwargs)
        self.db = self.db_client.napps
        self.transaction_lock = Lock()

    def bootstrap_indexes(self) -> None:
        """Bootstrap all topology related indexes."""
        index_tuples = [
            ("switches", "interfaces.id", pymongo.ASCENDING),
            ("links", "endpoints.id", pymongo.ASCENDING),
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
                {"$project": SwitchDoc.projection()},
            ]
        )
        return {"switches": {value["id"]: value for value in switches}}

    def get_links(self) -> dict:
        """Get links from DB."""
        links = self.db.links.aggregate(
            [
                {"$sort": {"_id": 1}},
                {"$project": LinkDoc.projection()},
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

    def upsert_switch(self, dpid: str, switch_dict: dict, **kwargs) -> Optional[dict]:
        """Update or insert switch."""
        utc_now = datetime.utcnow()
        model = SwitchDoc(**{**switch_dict, **{"_id": dpid, "updated_at": utc_now}})
        updated = self.db.switches.find_one_and_update(
            {"_id": dpid},
            {
                "$set": model.dict(exclude={"inserted_at"}),
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.AFTER,
            upsert=True,
            **kwargs,
        )
        return updated

    def bulk_update_interfaces_links(
        self, dpid: str, switch_dict: dict, links_dict: List[dict]
    ) -> None:
        """Bulk update interfaces links.

        Interfaces are bulk updated by updating the entire switch document
        it's easier than managing bulk query update operators for now.
        """

        utc_now = datetime.utcnow()

        link_ops = []
        for link_dict in links_dict:
            endpoint_a = link_dict.get("endpoint_a")
            endpoint_b = link_dict.get("endpoint_b")
            model = LinkDoc(
                **{
                    **link_dict,
                    **{
                        "updated_at": utc_now,
                        "_id": link_dict.get("id"),
                        "endpoints": [endpoint_a, endpoint_b],
                    },
                }
            )
            link_ops.append(
                ReplaceOne(
                    {"_id": model.id}, model.dict(exclude={"inserted_at"}), upsert=False
                )
            )

        # could get rid of this
        with self.transaction_lock:
            with self.db_client.start_session() as session:
                with session.start_transaction():
                    self.upsert_switch(dpid, switch_dict, session=session)
                    self.db.links.bulk_write(link_ops, ordered=False, session=session)

    def enable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and enable it."""
        return self._update_switch(dpid, {"$set": {"enabled": True}})

    def deactivate_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and deactivate it."""
        return self._update_switch(dpid, {"$set": {"active": False}})

    def disable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and disable it."""
        return self._update_switch(
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
        return self._update_interface(interface_id, {"$set": {"enabled": True}})

    def disable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to disable one interface and its embedded object on links."""
        return self._update_interface(interface_id, {"$set": {"enabled": False}})

    def activate_interface(self, interface_id: str) -> Optional[dict]:
        """Try to activate one interface."""
        return self._update_interface(interface_id, {"$set": {"active": True}})

    def deactivate_interface(self, interface_id: str) -> Optional[dict]:
        """Try to deactivate one interface."""
        return self._update_interface(interface_id, {"$set": {"active": False}})

    def enable_interface_lldp(self, interface_id: str) -> Optional[dict]:
        """Try to enable LLDP one interface."""
        return self._update_interface(interface_id, {"$set": {"lldp": True}})

    def disable_interface_lldp(self, interface_id: str) -> Optional[dict]:
        """Try to disable LLDP one interface."""
        return self._update_interface(interface_id, {"$set": {"lldp": False}})

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

        # could get rid of this too
        with self.transaction_lock:
            with self.db_client.start_session() as session:
                with session.start_transaction():
                    updated = self.db.switches.find_one_and_update(
                        {"interfaces.id": interface_id},
                        interfaces_expression,
                        return_document=ReturnDocument.AFTER,
                        session=session,
                    )
                    self.db.links.find_one_and_update(
                        {"endpoints.id": interface_id},
                        links_expression,
                        return_document=ReturnDocument.AFTER,
                        session=session,
                    )
                    return updated

    def upsert_link(self, link_id: str, link_dict: dict) -> dict:
        """Update or insert a Link."""
        utc_now = datetime.utcnow()

        endpoint_a = link_dict.get("endpoint_a")
        endpoint_b = link_dict.get("endpoint_b")
        model = LinkDoc(
            **{
                **link_dict,
                **{
                    "updated_at": utc_now,
                    "_id": link_id,
                    "endpoints": [endpoint_a, endpoint_b],
                },
            }
        )
        with self.transaction_lock:
            with self.db_client.start_session() as session:
                with session.start_transaction():
                    updated = self.db.links.find_one_and_update(
                        {"_id": link_id},
                        {
                            "$set": model.dict(exclude={"inserted_at"}),
                            "$setOnInsert": {"inserted_at": utc_now},
                        },
                        return_document=ReturnDocument.AFTER,
                        upsert=True,
                        session=session,
                    )
                    self.db.switches.find_one_and_update(
                        {"interfaces.id": endpoint_a},
                        {
                            "$set": {
                                "interfaces.$.link_id": link_id,
                                "updated_at": utc_now,
                            }
                        },
                        session=session,
                    )
                    self.db.switches.find_one_and_update(
                        {"interfaces.id": endpoint_b},
                        {
                            "$set": {
                                "interfaces.$.link_id": link_id,
                                "updated_at": utc_now,
                            }
                        },
                        session=session,
                    )
                    return updated

    def _update_link(self, link_id: str, update_expr: dict) -> Optional[dict]:
        """Try to find one link and update it given an update expression."""
        self._set_updated_at(update_expr)
        return self.db.links.find_one_and_update({"_id": link_id}, update_expr)

    def activate_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and activate it."""
        return self._update_link(
            link_id, {"$set": {"active": True, "metadata.last_status_is_active": True}}
        )

    def deactivate_link(self, link_id: str, interface_id: str) -> Optional[dict]:
        """Try to find one link and deactivate it."""
        return self._update_link(
            link_id,
            {"$set": {"active": False, "metadata.last_status_is_active": False}},
        )

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

    def delete_link_metadata_key(self, link_id: str, key: str) -> Optional[dict]:
        """Try to find a link and delete a metadata key."""
        return self._update_link(link_id, {"$unset": {f"metadata.{key}": ""}})

    def bulk_upsert_interface_details(
        self, ids_details: Tuple[str, dict]
    ) -> Optional[dict]:
        """Update or insert interfaces details."""
        utc_now = datetime.utcnow()
        ops = []
        for _id, detail_dict in ids_details:
            ops.append(
                UpdateOne(
                    {"_id": _id},
                    {
                        "$set": InterfaceDetailDoc(
                            **{
                                **detail_dict,
                                **{
                                    "updated_at": utc_now,
                                    "_id": _id,
                                },
                            }
                        ).dict(exclude={"inserted_at"}),
                        "$setOnInsert": {"inserted_at": utc_now},
                    },
                    upsert=True,
                ),
            )

        with self.transaction_lock:
            with self.db_client.start_session() as session:
                with session.start_transaction():
                    return self.db.interface_details.bulk_write(
                        ops, ordered=False, session=session
                    )

    def get_interfaces_details(self, interface_ids: List[str]) -> Optional[dict]:
        """Try to get interfaces details given a list of interface ids."""
        return self.db.interface_details.aggregate(
            [
                {"$match": {"_id": {"$in": interface_ids}}},
            ]
        )
