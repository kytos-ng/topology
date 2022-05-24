"""Module to TopoController."""

from unittest import TestCase
from unittest.mock import MagicMock

from pymongo.operations import UpdateOne

from napps.kytos.topology.controllers import TopoController
from napps.kytos.topology.db.models import LinkDoc, SwitchDoc


class TestTopoController(TestCase):  # pylint: disable=too-many-public-methods
    """Test the Main class."""

    def setUp(self) -> None:
        """Execute steps before each tests."""
        self.topo = TopoController(MagicMock())
        self.dpid = "00:00:00:00:00:00:00:01"
        self.interface_id = f"{self.dpid}:1"
        self.link_id = "some_id"

    def test_boostrap_indexes(self) -> None:
        """Test_boostrap_indexes."""
        self.topo.bootstrap_indexes()

        expected_indexes = [
            ("switches", [("interfaces.id", 1)]),
            ("links", [("endpoints.id", 1)]),
        ]
        mock = self.topo.mongo.bootstrap_index
        assert mock.call_count == len(expected_indexes)
        indexes = [(v[0][0], v[0][1]) for v in mock.call_args_list]
        assert expected_indexes == indexes

    def test_get_topology(self) -> None:
        """Test_get_topology."""
        self.topo.get_switches = MagicMock()
        self.topo.get_links = MagicMock()
        assert "topology" in self.topo.get_topology()
        assert self.topo.get_switches.call_count == 1
        assert self.topo.get_links.call_count == 1

    def test_get_links(self) -> None:
        """test_get_links."""
        assert "links" in self.topo.get_links()
        assert self.topo.db.links.aggregate.call_count == 1
        arg = self.topo.db.links.aggregate.call_args[0]
        assert arg[0] == [{"$sort": {"_id": 1}},
                          {"$project": LinkDoc.projection()}]

    def test_get_switches(self) -> None:
        """test_get_switches."""
        assert "switches" in self.topo.get_switches()
        assert self.topo.db.switches.aggregate.call_count == 1
        arg = self.topo.db.switches.aggregate.call_args[0]
        assert arg[0] == [
            {"$sort": {"_id": 1}},
            {"$project": SwitchDoc.projection()},
        ]

    def test_get_interfaces(self) -> None:
        """test_get_interfaces."""
        assert "interfaces" in self.topo.get_interfaces()
        assert self.topo.db.switches.aggregate.call_count == 1
        arg = self.topo.db.switches.aggregate.call_args[0]
        assert arg[0] == [
            {"$sort": {"_id": 1}},
            {"$project": {"interfaces": 1, "_id": 0}},
            {"$unwind": "$interfaces"},
            {"$replaceRoot": {"newRoot": "$interfaces"}},
        ]

    def test_enable_switch(self) -> None:
        """test_enable_switch."""
        self.topo.enable_switch(self.dpid)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.dpid}
        assert arg2["$set"]["enabled"]

    def test_disable_switch(self) -> None:
        """test_disable_switch."""
        self.topo.disable_switch(self.dpid)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.dpid}
        assert not arg2["$set"]["enabled"]

    def test_deactivate_switch(self) -> None:
        """test_deactivate_switch."""
        self.topo.deactivate_switch(self.dpid)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.dpid}
        assert not arg2["$set"]["active"]

    def test_add_switch_metadata(self) -> None:
        """test_add_switch_metadata."""
        metadata = {"some": "value"}
        self.topo.add_switch_metadata(self.dpid, metadata)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.dpid}
        assert arg2["$set"]["metadata.some"] == "value"

    def test_delete_switch_metadata(self) -> None:
        """test_delete_switch_metadata."""
        key = "some"
        self.topo.delete_switch_metadata_key(self.dpid, key)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.dpid}
        assert arg2["$unset"][f"metadata.{key}"] == ""

    def test_enable_interface(self) -> None:
        """test_enable_interface."""
        self.topo.enable_interface(self.interface_id)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"interfaces.id": self.interface_id}
        assert arg2["$set"]["interfaces.$.enabled"]

    def test_disable_interface(self) -> None:
        """test_disable_interface."""
        self.topo.disable_interface(self.interface_id)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"interfaces.id": self.interface_id}
        assert not arg2["$set"]["interfaces.$.enabled"]

    def test_activate_interface(self) -> None:
        """test_activate_interface."""
        self.topo.activate_interface(self.interface_id)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"interfaces.id": self.interface_id}
        assert arg2["$set"]["interfaces.$.active"]

    def test_deactivate_interface(self) -> None:
        """test_deactivate_interface."""
        self.topo.deactivate_interface(self.interface_id)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"interfaces.id": self.interface_id}
        assert not arg2["$set"]["interfaces.$.active"]

    def test_activate_link(self) -> None:
        """test activate_link."""
        mock = MagicMock()
        self.topo._update_link = mock
        self.topo.activate_link(self.link_id, last_status_change=1,
                                last_status_is_active=True)
        self.topo._update_link.assert_called_with(
            self.link_id,
            {
                "$set": {
                    "metadata.last_status_change": 1,
                    "metadata.last_status_is_active": True,
                    "active": True,
                }
            },
        )

    def test_deactivate_link(self) -> None:
        """test deactivate_link."""
        mock = MagicMock()
        self.topo._update_link = mock
        self.topo.deactivate_link(self.link_id, last_status_change=1,
                                  last_status_is_active=False)
        self.topo._update_link.assert_called_with(
            self.link_id,
            {
                "$set": {
                    "metadata.last_status_change": 1,
                    "metadata.last_status_is_active": False,
                    "active": False,
                }
            },
        )

    def test_add_interface_metadata(self) -> None:
        """test_add_interface_metadata."""
        metadata = {"some": "value"}
        self.topo.add_interface_metadata(self.interface_id, metadata)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"interfaces.id": self.interface_id}
        assert arg2["$set"]["interfaces.$.metadata.some"] == "value"

    def test_delete_interface_metadata_key(self) -> None:
        """test_delete_interface_metadata."""
        key = "some"
        self.topo.delete_interface_metadata_key(self.interface_id, key)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"interfaces.id": self.interface_id}
        assert arg2["$unset"][f"interfaces.$.metadata.{key}"] == ""

    def test_enable_link(self) -> None:
        """test_enable_link."""
        self.topo.enable_link(self.link_id)

        self.topo.db.links.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.links.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.link_id}
        assert arg2["$set"]["enabled"]

    def test_disable_link(self) -> None:
        """test_disable_link."""
        self.topo.disable_link(self.link_id)

        self.topo.db.links.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.links.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.link_id}
        assert not arg2["$set"]["enabled"]

    def test_add_link_metadata(self) -> None:
        """test_add_link_metadata."""
        key = "some_key"
        value = "some_value"
        self.topo.add_link_metadata(self.link_id, {key: value})

        self.topo.db.links.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.links.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.link_id}
        assert arg2["$set"][f"metadata.{key}"] == value

    def test_delete_link_metadata_key(self) -> None:
        """test_delete_link_metadata_key."""
        key = "some_key"
        self.topo.delete_link_metadata_key(self.link_id, key)

        self.topo.db.links.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.links.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.link_id}
        assert arg2["$unset"][f"metadata.{key}"] == ""

    def test_get_interfaces_details(self) -> None:
        """test_get_insterfaces_details."""
        interfaces_ids = ["1", "2", "3"]
        self.topo.get_interfaces_details(interfaces_ids)
        self.topo.db.interface_details.aggregate.assert_called_with(
            [{"$match": {"_id": {"$in": interfaces_ids}}}]
        )

    def test_bulk_upsert_interface_details(self) -> None:
        """test_bulk_upsert_interface_details."""
        ids_details = [
            ("1", {"_id": "1", "available_vlans": [1]}),
            ("2", {"_id": "2", "available_vlans": [2]}),
        ]
        self.topo.bulk_upsert_interface_details(ids_details)

        self.topo.db_client.start_session.assert_called()
        arg1 = self.topo.db.interface_details.bulk_write.call_args[0]
        assert len(arg1[0]) == len(ids_details)
        for item in arg1[0]:
            assert isinstance(item, UpdateOne)

    def test_upsert_switch(self) -> None:
        """test_upsert_switch."""
        switch_dict = {"enabled": True, "active": True, "_id": self.dpid}
        self.topo.upsert_switch(self.dpid, switch_dict)

        self.topo.db.switches.find_one_and_update.assert_called()
        arg1, arg2 = self.topo.db.switches.find_one_and_update.call_args[0]
        assert arg1 == {"_id": self.dpid}
        for key, value in switch_dict.items():
            assert arg2["$set"][key] == value

    def test_upsert_link(self) -> None:
        """test_upsert_link."""
        link_dict = {
            "_id": self.link_id,
            "enabled": True,
            "active": True,
            "endpoint_a": {"id": "00:00:00:00:00:00:00:01:1"},
            "endpoint_b": {"id": "00:00:00:00:00:00:00:02:01"},
        }
        self.topo.upsert_link(self.link_id, link_dict)
        assert self.topo.db.switches.find_one_and_update.call_count == 2
        assert self.topo.db.links.find_one_and_update.call_count == 1
