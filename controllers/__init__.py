"""TopoController."""

# pylint: disable=invalid-name
import os
import re
from datetime import datetime
from threading import Lock
from typing import List, Optional, Tuple

import pymongo
from pymongo.collection import ReturnDocument
from pymongo.errors import ConnectionFailure, ExecutionTimeout
from pymongo.operations import UpdateOne
from tenacity import retry_if_exception_type, stop_after_attempt, wait_random

from kytos.core import log
from kytos.core.db import Mongo
from kytos.core.retry import before_sleep, for_all_methods, retries
from napps.kytos.topology.db.models import (InterfaceDetailDoc, LinkDoc,
                                            SwitchDoc)


@for_all_methods(
    retries,
    stop=stop_after_attempt(
        int(os.environ.get("MONGO_AUTO_RETRY_STOP_AFTER_ATTEMPT", 3))
    ),
    wait=wait_random(
        min=int(os.environ.get("MONGO_AUTO_RETRY_WAIT_RANDOM_MIN", 0.1)),
        max=int(os.environ.get("MONGO_AUTO_RETRY_WAIT_RANDOM_MAX", 1)),
    ),
    before_sleep=before_sleep,
    retry=retry_if_exception_type((ConnectionFailure, ExecutionTimeout)),
)
class TopoController:
    """TopoController."""

    def __init__(self, get_mongo=Mongo) -> None:
        """Constructor of TopoController."""
        self.mongo = get_mongo()
        self.db_client = self.mongo.client
        self.db = self.db_client[self.mongo.db_name]

    def bootstrap_indexes(self) -> None:
        """Bootstrap all topology related indexes."""
        index_tuples = [
            ("switches", [("interfaces.id", pymongo.ASCENDING)]),
            ("links", [("endpoints.id", pymongo.ASCENDING)]),
        ]
        for collection, keys in index_tuples:
            if self.mongo.bootstrap_index(collection, keys):
                log.info(
                    f"Created DB index {keys}, collection: {collection})"
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

    @staticmethod
    def _set_updated_at(update_expr: dict) -> None:
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
        updated = self.db.switches.find_one_and_update(
            {"_id": dpid},
            {
                "$set": model.model_dump(exclude={"inserted_at"}),
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.AFTER,
            upsert=True,
        )
        return updated

    def enable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and enable it."""
        return self._update_switch(dpid, {"$set": {"enabled": True}})

    def disable_switch(self, dpid: str) -> Optional[dict]:
        """Try to find one switch and disable it."""
        return self._update_switch(
            dpid, {"$set": {"enabled": False, "interfaces.$[].enabled": False}}
        )

    def add_switch_metadata(self, dpid: str, metadata: dict) -> Optional[dict]:
        """Try to find a switch and add to its metadata."""
        update_expr = {
            "$set": {f"metadata.{k}": v for k, v in metadata.items()}
        }
        return self._update_switch(dpid, update_expr)

    def delete_switch_metadata_key(
        self, dpid: str, key: str
    ) -> Optional[dict]:
        """Try to find a switch and delete a metadata key."""
        return self._update_switch(dpid, {"$unset": {f"metadata.{key}": ""}})

    def enable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to enable one interface and its embedded object on links."""
        return self._update_interface(
            interface_id, {"$set": {"enabled": True}}
        )

    def disable_interface(self, interface_id: str) -> Optional[dict]:
        """Try to disable one interface and its embedded object on links."""
        return self._update_interface(
            interface_id, {"$set": {"enabled": False}}
        )
    
    def delete_interface(self, interface_id: str) -> Optional[dict]:
        """Try to delete an interface embedded in a switch."""
        switch_id, _, port_num = interface_id.rsplit(":")
        port_num = int(port_num)
        return self.db.switches.find_one_and_update(
            {"_id": switch_id},
            {"$unset": {"interfaces.$[iface]": 1}},
            array_filters=[{
                "iface.port_number": {"$eq": port_num}
            }],
            return_document=ReturnDocument.AFTER
        )

    def add_interface_metadata(
        self, interface_id: str, metadata: dict
    ) -> Optional[dict]:
        """Try to find an interface and add to its metadata."""
        update_expr = {
            "$set": {f"metadata.{k}": v for k, v in metadata.items()}
        }
        return self._update_interface(interface_id, update_expr)

    def delete_interface_metadata_key(
        self, interface_id: str, key: str
    ) -> Optional[dict]:
        """Try to find an interface and delete a metadata key."""
        return self._update_interface(
            interface_id, {"$unset": {f"metadata.{key}": ""}}
        )

    def _update_interface(
        self, interface_id: str, update_expr: dict
    ) -> Optional[dict]:
        """Try to update one interface and its embedded object on links."""
        self._set_updated_at(update_expr)
        interfaces_expression = {}
        for operator, values in update_expr.items():
            interfaces_expression[operator] = {
                f"interfaces.$.{k}": v for k, v in values.items()
            }
        return self.db.switches.find_one_and_update(
            {"interfaces.id": interface_id},
            interfaces_expression,
            return_document=ReturnDocument.AFTER,
        )

    def enable_interfaces(
        self,
        switch_id: str,
        ports: list[int]
    ):
        """Try to enable several interfaces and their embedded objects."""
        return self._update_interfaces_of_switch(
            switch_id, ports, {"$set": {"enabled": True}}
        )

    def disable_interfaces(
        self,
        switch_id: str,
        ports: list[int]
    ):
        """Try to disable several interfaces and their embedded objects."""
        return self._update_interfaces_of_switch(
            switch_id, ports, {"$set": {"enabled": False}}
        )

    def _update_interfaces_of_switch(
        self,
        switch_id: str,
        ports: list[int],
        update_expr: dict
    ):
        self._set_updated_at(update_expr)
        interfaces_expression = {}
        for operator, values in update_expr.items():
            interfaces_expression[operator] = {
                f"interfaces.$[iface].{key}": value
                for key, value in values.items()
            }

        return self.db.switches.find_one_and_update(
            {"_id": switch_id},
            interfaces_expression,
            array_filters=[{
                "iface.port_number": {"$in": ports}
            }],
            return_document=ReturnDocument.AFTER
        )

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
        updated = self.db.links.find_one_and_update(
            {"_id": link_id},
            {
                "$set": model.model_dump(exclude={"inserted_at"}),
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.AFTER,
            upsert=True,
        )
        self.db.switches.find_one_and_update(
            {"interfaces.id": endpoint_a},
            {
                "$set": {
                    "interfaces.$.link_id": link_id,
                    "interfaces.$.link_side": "endpoint_a",
                    "updated_at": utc_now,
                }
            },
        )
        self.db.switches.find_one_and_update(
            {"interfaces.id": endpoint_b},
            {
                "$set": {
                    "interfaces.$.link_id": link_id,
                    "interfaces.$.link_side": "endpoint_b",
                    "updated_at": utc_now,
                }
            },
        )
        return updated

    def _update_link(self, link_id: str, update_expr: dict) -> Optional[dict]:
        """Try to find one link and update it given an update expression."""
        self._set_updated_at(update_expr)
        return self.db.links.find_one_and_update({"_id": link_id}, update_expr)

    def enable_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and enable it."""
        return self._update_link(link_id, {"$set": {"enabled": True}})

    def disable_link(self, link_id: str) -> Optional[dict]:
        """Try to find one link and disable it."""
        return self._update_link(link_id, {"$set": {"enabled": False}})

    def bulk_disable_links(self, link_ids: set[str]) -> int:
        """Bulk update that disables found links."""
        if not link_ids:
            return 0
        ops = []
        for _id in link_ids:
            ops.append(
                UpdateOne(
                    {"_id": _id},
                    {
                        "$set":
                        {
                            "updated_at": datetime.utcnow(),
                            "enabled": False,
                        }
                    }
                )
            )
        return self.db.links.bulk_write(ops).modified_count

    def add_link_metadata(
        self, link_id: str, metadata: dict
    ) -> Optional[dict]:
        """Try to find link and add to its metadata."""
        update_expr = {
            "$set": {f"metadata.{k}": v for k, v in metadata.items()}
        }
        return self._update_link(link_id, update_expr)

    def delete_link_metadata_key(
        self, link_id: str, key: str
    ) -> Optional[dict]:
        """Try to find a link and delete a metadata key."""
        return self._update_link(link_id, {"$unset": {f"metadata.{key}": ""}})

    def bulk_delete_link_metadata_key(
        self, link_ids: List[str], key: str
    ) -> Optional[dict]:
        """Bulk delelete link metadata key."""
        update_expr = {"$unset": {f"metadata.{key}": 1}}
        self._set_updated_at(update_expr)
        return self.db.links.update_many({"_id": {"$in": link_ids}},
                                         update_expr)

    # pylint: disable=too-many-arguments
    def upsert_interface_details(
        self,
        id_: str,
        available_tags: dict[str, list[list[int]]],
        tag_ranges: dict[str, list[list[int]]],
        default_tag_ranges: dict[str, list[list[int]]],
        special_available_tags: dict[str, list[str]],
        special_tags: dict[str, list[str]],
        default_special_tags: dict[str, list[str]],
        supported_tag_types: list[str],
    ) -> Optional[dict]:
        """Update or insert interfaces details."""
        utc_now = datetime.utcnow()
        model = InterfaceDetailDoc(**{
                "_id": id_,
                "available_tags": available_tags,
                "tag_ranges": tag_ranges,
                "default_tag_ranges": default_tag_ranges,
                "special_available_tags": special_available_tags,
                "special_tags": special_tags,
                "default_special_tags": default_special_tags,
                "supported_tag_types": supported_tag_types,
                "updated_at": utc_now
        }).model_dump(exclude={"inserted_at"})
        updated = self.db.interface_details.find_one_and_update(
            {"_id": id_},
            {
                "$set": model,
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.AFTER,
            upsert=True,
        )
        return updated

    def get_interfaces_details(
        self, interface_ids: List[str]
    ) -> Optional[dict]:
        """Try to get interfaces details given a list of interface ids."""
        return self.db.interface_details.aggregate(
            [
                {"$match": {"_id": {"$in": interface_ids}}},
            ]
        )

    def delete_link(self, link_id: str) -> Optional[dict]:
        """Delete a link by its id."""
        return self.db.links.find_one_and_delete(
            {"_id": link_id}
        )

    def delete_switch_data(
        self,
        switch_dpid: str
    ) -> tuple[Optional[dict], int]:
        """Delete a switch related data in database."""
        regex = re.compile(rf'^{switch_dpid}:\d+$')
        det_result = self.db.interface_details.delete_many(
            {"_id": {"$regex": regex}}
        )
        swt_result = self.db.switches.find_one_and_delete(
            {"_id": switch_dpid}
        )
        return (swt_result, det_result.deleted_count)

    def delete_interface_from_details(self, intf_id: str) -> Optional[dict]:
        """Delete interface from interface_details."""
        return self.db.interface_details.find_one_and_delete(
            {"_id": intf_id}
        )

    # pylint: disable=too-many-arguments
    def upsert_link_details(
        self,
        id_: str,
        available_tags: dict[str, list[list[int]]],
        tag_ranges: dict[str, list[list[int]]],
        default_tag_ranges: dict[str, list[list[int]]],
        special_available_tags: dict[str, list[str]],
        special_tags: dict[str, list[str]],
        default_special_tags: dict[str, list[str]],
        supported_tag_types: list[str],
    ) -> Optional[dict]:
        """Update or insert link details."""
        utc_now = datetime.utcnow()
        model = InterfaceDetailDoc(**{
                "_id": id_,
                "available_tags": available_tags,
                "tag_ranges": tag_ranges,
                "default_tag_ranges": default_tag_ranges,
                "special_available_tags": special_available_tags,
                "special_tags": special_tags,
                "default_special_tags": default_special_tags,
                "supported_tag_types": supported_tag_types,
                "updated_at": utc_now
        }).model_dump(exclude={"inserted_at"})
        updated = self.db.link_details.find_one_and_update(
            {"_id": id_},
            {
                "$set": model,
                "$setOnInsert": {"inserted_at": utc_now},
            },
            return_document=ReturnDocument.AFTER,
            upsert=True,
        )
        return updated

    def get_links_details(
        self, link_ids: List[str]
    ) -> Optional[dict]:
        """Try to get link details given a list of link ids."""
        return self.db.link_details.aggregate(
            [
                {"$match": {"_id": {"$in": link_ids}}},
            ]
        )

    def delete_link_from_details(self, link_id: str) -> Optional[dict]:
        """Delete link from link_details."""
        return self.db.link_details.find_one_and_delete(
            {"_id": link_id}
        )
