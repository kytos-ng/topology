"""Module to test the main napp file."""
# pylint: disable=import-error,no-name-in-module,wrong-import-order
# pylint: disable=import-outside-toplevel,attribute-defined-outside-init
import asyncio
import pytest
import time
from datetime import timedelta
from unittest.mock import MagicMock, create_autospec, patch, call, Mock
import tenacity
from kytos.core.common import EntityStatus
from kytos.core.helpers import now
from kytos.core.events import KytosEvent
from kytos.core.exceptions import (KytosSetTagRangeError,
                                   KytosTagtypeNotSupported)
from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.switch import Switch
from kytos.lib.helpers import (get_interface_mock, get_link_mock,
                               get_controller_mock, get_switch_mock,
                               get_test_client)
from napps.kytos.topology.exceptions import RestoreError


@pytest.mark.parametrize("liveness_status, status",
                         [("up", EntityStatus.UP),
                          ("down", EntityStatus.DOWN)])
def test_handle_link_liveness_status(liveness_status, status) -> None:
    """Test handle link liveness."""
    from napps.kytos.topology.main import Main
    napp = Main(get_controller_mock())
    napp.notify_topology_update = MagicMock()
    napp.notify_link_status_change = MagicMock()

    link = MagicMock(id="some_id", status=status)
    napp.handle_link_liveness_status(link, liveness_status)

    link.extend_metadata.assert_called_with({"liveness_status":
                                             liveness_status})
    assert napp.notify_topology_update.call_count == 1
    assert napp.notify_link_status_change.call_count == 1
    reason = f"liveness_{liveness_status}"
    napp.notify_link_status_change.assert_called_with(link, reason=reason)


# pylint: disable=too-many-public-methods
class TestMain:
    """Test the Main class."""

    # pylint: disable=too-many-public-methods, protected-access,C0302

    def setup_method(self):
        """Execute steps before each tests."""
        patch('kytos.core.helpers.run_on_thread', lambda x: x).start()
        # pylint: disable=import-outside-toplevel
        from napps.kytos.topology.main import Main
        Main.get_topo_controller = MagicMock()
        controller = get_controller_mock()
        self.napp = Main(controller)
        self.api_client = get_test_client(controller, self.napp)
        self.base_endpoint = 'kytos/topology/v3'

    def test_get_event_listeners(self):
        """Verify all event listeners registered."""
        expected_events = [
            'kytos/core.shutdown',
            'kytos/core.shutdown.kytos/topology',
            '.*.topo_controller.upsert_switch',
            '.*.of_lldp.network_status.updated',
            '.*.interface.is.nni',
            '.*.connection.lost',
            '.*.switch.interfaces.created',
            '.*.topology.switch.interface.created',
            '.*.switch.interface.deleted',
            '.*.switch.interface.link_down',
            '.*.switch.interface.link_up',
            '.*.switch.(new|reconnected)',
            'kytos/.*.liveness.(up|down|disabled)',
            '.*.switch.port.created',
            'kytos/topology.notify_link_up_if_status',
            'topology.interruption.(start|end)',
            'kytos/core.interface_tags',
            'kytos/core.link_tags',
        ]
        actual_events = self.napp.listeners()
        assert sorted(expected_events) == sorted(actual_events)

    async def test_get_topology(self):
        """Test get_topology."""
        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_b = "00:00:00:00:00:00:00:02"
        expected = {
                      "topology": {
                        "switches": {
                          "00:00:00:00:00:00:00:01": {
                            "metadata": {
                              "lat": "0.0",
                              "lng": "-30.0"
                            }
                          },
                          "00:00:00:00:00:00:00:02": {
                            "metadata": {
                              "lat": "0.0",
                              "lng": "-30.0"
                            }
                          }
                        },
                        "links": {
                          "cf0f4071be4": {
                            "id": "cf0f4071be4"
                          }
                        }
                      }
                    }

        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_switch_b = get_switch_mock(dpid_b, 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)

        mock_link = get_link_mock(mock_interface_a, mock_interface_b)
        mock_link.id = 'cf0f4071be4'
        mock_switch_a.id = dpid_a
        mock_switch_a.as_dict.return_value = {'metadata': {'lat': '0.0',
                                              'lng': '-30.0'}}
        mock_switch_b.id = dpid_b
        mock_switch_b.as_dict.return_value = {'metadata': {'lat': '0.0',
                                              'lng': '-30.0'}}

        self.napp.controller.switches = {dpid_a: mock_switch_a,
                                         dpid_b: mock_switch_b}

        self.napp.controller.links = {"cf0f4071be4": mock_link}
        mock_link.as_dict.return_value = {"id": "cf0f4071be4"}
        endpoint = f"{self.base_endpoint}/"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == expected

    def test_load_topology(self):
        """Test load_topology."""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        link_id = \
            'cf0f4071be426b3f745027f5d22bc61f8312ae86293c9b28e7e66015607a9260'
        dpid_a = '00:00:00:00:00:00:00:01'
        dpid_b = '00:00:00:00:00:00:00:02'
        topology = {
            "topology": {
                "links": {
                    link_id: {
                        "enabled": True,
                        "id": link_id,
                        "endpoint_a": {"id": f"{dpid_a}:2"},
                        "endpoint_b": {"id": f"{dpid_b}:2"},
                    }
                },
                "switches": {
                    dpid_a: {
                        "dpid": dpid_a,
                        "enabled": True,
                        "metadata": {},
                        "id": dpid_a,
                        "interfaces": {
                            f"{dpid_a}:2": {
                                "enabled": True,
                                "metadata": {},
                                "lldp": True,
                                "port_number": 2,
                                "name": "s1-eth2",
                            }
                        },
                    },
                    dpid_b: {
                        "dpid": dpid_b,
                        "enabled": True,
                        "metadata": {},
                        "id": dpid_b,
                        "interfaces": {
                            f"{dpid_b}:2": {
                                "enabled": True,
                                "metadata": {},
                                "lldp": True,
                                "port_number": 2,
                                "name": "s2-eth2",
                            }
                        },
                    },
                },
            }
        }
        switches_expected = [dpid_a, dpid_b]
        interfaces_expected = [f'{dpid_a}:2', f'{dpid_b}:2']
        links_expected = [link_id]
        self.napp.topo_controller.get_topology.return_value = topology
        self.napp.load_topology()
        assert switches_expected == list(self.napp.controller.switches.keys())
        interfaces = []
        for switch in self.napp.controller.switches.values():
            for iface in switch.interfaces.values():
                interfaces.append(iface.id)
        assert interfaces_expected == interfaces
        assert links_expected == list(self.napp.controller.links.keys())
        assert mock_buffers_put.call_args[1] == {"timeout": 1}

    def test_load_topology_does_nothing(self):
        """Test _load_network_status doing nothing."""
        self.napp.topo_controller.get_topology.return_value = {
            "topology": {"switches": {}, "links": {}}
        }
        self.napp.topo_controller.load_topology()
        assert not self.napp.controller.switches
        assert not self.napp.controller.links

    def test_load_switch_fail(self):
        """Test load_topology failure in switch."""
        switches = {
            "1": {}
        }
        success, failure = self.napp._load_switches(
            switches
        )
        assert "1" in failure
        assert "1" not in success

    def test_load_link_fail(self):
        """Test load_topology failure in link."""
        links = {
            "1": {}
        }
        success, failure = self.napp._load_links(
            links
        )
        assert "1" in failure
        assert "1" not in success

    @patch('napps.kytos.topology.main.KytosEvent')
    def test_load_switch(self, mock_event):
        """Test _load_switch."""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_x = "00:00:00:00:00:00:00:XX"
        iface_a = f'{dpid_a}:1'
        switch_attrs = {
            'dpid': dpid_a,
            'enabled': True,
            'id': dpid_a,
            'metadata': {},
            'interfaces': {
                iface_a: {
                    'enabled': True,
                    'active': True,
                    'lldp': True,
                    'id': iface_a,
                    'switch': dpid_a,
                    'metadata': {},
                    'name': 's2-eth1',
                    'port_number': 1
                }
            }
        }
        self.napp._load_switches({dpid_a: switch_attrs})

        assert len(self.napp.controller.switches) == 1
        assert dpid_a in self.napp.controller.switches
        assert dpid_x not in self.napp.controller.switches
        switch = self.napp.controller.switches[dpid_a]

        assert switch.id == dpid_a
        assert switch.dpid == dpid_a
        assert switch.is_enabled()
        assert not switch.is_active()

        assert len(switch.interfaces) == 1
        assert 1 in switch.interfaces
        assert 2 not in switch.interfaces
        mock_event.assert_called()
        mock_buffers_put.assert_called()
        assert mock_buffers_put.call_args[1] == {"timeout": 1}

        interface = switch.interfaces[1]
        assert interface.id == iface_a
        assert interface.switch.id == dpid_a
        assert interface.port_number == 1
        assert interface.is_enabled()
        assert not interface.is_active()
        assert interface.lldp
        assert interface.uni
        assert not interface.nni

    def test_load_switch_attrs(self):
        """Test _load_switch."""
        dpid_b = "00:00:00:00:00:00:00:02"
        iface_b = f'{dpid_b}:1'
        switch_attrs = {
            "active": True,
            "connection": "127.0.0.1:43230",
            "data_path": "XX Human readable desc of dp",
            "dpid": "00:00:00:00:00:00:00:02",
            "enabled": False,
            "hardware": "Open vSwitch",
            "id": "00:00:00:00:00:00:00:02",
            "interfaces": {
                "00:00:00:00:00:00:00:02:1": {
                    "active": True,
                    "enabled": False,
                    "id": "00:00:00:00:00:00:00:02:1",
                    "link": "",
                    "lldp": False,
                    "mac": "de:58:c3:30:b7:b7",
                    "metadata": {},
                    "name": "s2-eth1",
                    "nni": False,
                    "port_number": 1,
                    "speed": 1250000000,
                    "switch": "00:00:00:00:00:00:00:02",
                    "type": "interface",
                    "uni": True
                },
            },
            "manufacturer": "Nicira, Inc.",
            "metadata": {},
            "name": "00:00:00:00:00:00:00:04",
            "ofp_version": "0x04",
            "serial": "XX serial number",
            "software": "2.10.7",
            "type": "switch"
        }

        assert len(self.napp.controller.switches) == 0
        self.napp._load_switches({dpid_b: switch_attrs})
        assert len(self.napp.controller.switches) == 1
        assert dpid_b in self.napp.controller.switches

        switch = self.napp.controller.switches[dpid_b]
        assert switch.id == dpid_b
        assert switch.dpid == dpid_b
        assert not switch.is_enabled()
        assert not switch.is_active()
        assert switch.description['manufacturer'] == 'Nicira, Inc.'
        assert switch.description['hardware'] == 'Open vSwitch'
        assert switch.description['software'] == '2.10.7'
        assert switch.description['serial'] == 'XX serial number'
        exp_data_path = 'XX Human readable desc of dp'
        assert switch.description['data_path'] == exp_data_path

        assert len(switch.interfaces) == 1
        assert 1 in switch.interfaces
        assert 2 not in switch.interfaces

        interface = switch.interfaces[1]
        assert interface.id == iface_b
        assert interface.switch.id == dpid_b
        assert interface.port_number == 1
        assert not interface.is_enabled()
        assert not interface.lldp
        assert interface.uni
        assert not interface.nni

    def test_load_interfaces_tags_values(self):
        """Test load_interfaces_tags_values."""
        dpid_a = "00:00:00:00:00:00:00:01"
        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_a.id = dpid_a + ':1'
        mock_switch_a.interfaces = {1: mock_interface_a}
        ava_tags = {'vlan': [[10, 4095]]}
        tag_ranges = {'vlan': [[5, 4095]]}
        special_available_tags = {'vlan': ["untagged", "any"]}
        special_tags = {'vlan': ["untagged", "any"]}
        supported_tag_types = ["vlan"]
        interface_details = [{
            "id": mock_interface_a.id,
            "available_tags": ava_tags,
            "tag_ranges": tag_ranges,
            "default_tag_ranges": tag_ranges,
            "special_available_tags": special_available_tags,
            "special_tags": special_tags,
            "default_special_tags": special_tags,
            "supported_tag_types": supported_tag_types,
        }]

        switch_interfaces = {
            interface.id: interface
            for interface in mock_switch_a.interfaces.values()
        }
        self.napp._load_details(
            switch_interfaces,
            interface_details
        )
        set_method = mock_interface_a.set_available_tags_tag_ranges
        set_method.assert_called_once_with(
            ava_tags, tag_ranges, tag_ranges,
            special_available_tags, special_tags, special_tags,
            frozenset(supported_tag_types),
        )

    def test_handle_on_interface_tags(self):
        """test_handle_on_interface_tags."""
        dpid_a = "00:00:00:00:00:00:00:01"
        available_tags = {'vlan': [[200, 3000]]}
        tag_ranges = {'vlan': [[20, 20], [200, 3000]]}
        special_available_tags = {'vlan': ["untagged", "any"]}
        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_a.available_tags = available_tags
        mock_interface_a.tag_ranges = tag_ranges
        mock_interface_a.special_available_tags = special_available_tags
        mock_interface_a.special_tags = special_available_tags
        self.napp.handle_on_interface_tags(mock_interface_a)
        tp_controller = self.napp.topo_controller
        args = tp_controller.upsert_interface_details.call_args[0]
        assert args[0] == '00:00:00:00:00:00:00:01:1'
        assert args[1] == {'vlan': [[200, 3000]]}
        assert args[2] == {'vlan': [[20, 20], [200, 3000]]}

    def test_load_link(self):
        """Test _load_link."""
        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_b = "00:00:00:00:00:00:00:02"
        link_id = '4d42dc08522'
        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_switch_b = get_switch_mock(dpid_b, 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_a.id = dpid_a + ':1'
        mock_interface_a.available_tags = [1, 2, 3]
        mock_interface_a.link = None
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_interface_b.id = dpid_b + ':1'
        mock_interface_b.available_tags = [1, 2, 3]
        mock_interface_b.link = None
        mock_switch_a.interfaces = {1: mock_interface_a}
        mock_switch_b.interfaces = {1: mock_interface_b}
        self.napp.controller.switches[dpid_a] = mock_switch_a
        self.napp.controller.switches[dpid_b] = mock_switch_b
        link_attrs = {
            'enabled': True,
            'id': link_id,
            'metadata': {},
            'endpoint_a': {
                'id': mock_interface_a.id
            },
            'endpoint_b': {
                'id': mock_interface_b.id
            }
        }

        self.napp._load_links({link_id: link_attrs})

        assert len(self.napp.controller.links) == 1
        link = list(self.napp.controller.links.values())[0]

        assert link.endpoint_a.id == mock_interface_a.id
        assert link.endpoint_b.id == mock_interface_b.id
        assert mock_interface_a.nni
        assert mock_interface_b.nni
        assert mock_interface_a.update_link.call_count == 1
        assert mock_interface_b.update_link.call_count == 1

        # test enable/disable
        link_id = '4d42dc08522'
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_link = get_link_mock(mock_interface_a, mock_interface_b)
        mock_link.id = link_id

        self.napp.controller.get_link_or_create = MagicMock()
        mock_get_link_or_create = self.napp.controller.get_link_or_create
        mock_get_link_or_create.return_value = (mock_link, True)

    def test_fail_load_link(self):
        """Test fail load_link."""
        self.napp.controller.get_link_or_create = MagicMock()
        mock_get_link_or_create = self.napp.controller.get_link_or_create
        dpid_a = '00:00:00:00:00:00:00:01'
        dpid_b = '00:00:00:00:00:00:00:02'
        link_id = '4d42dc08522'
        mock_switch_a = get_switch_mock(dpid_a)
        mock_switch_b = get_switch_mock(dpid_b)
        mock_interface_a_1 = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b_1 = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_link = get_link_mock(mock_interface_a_1, mock_interface_b_1)
        mock_link.id = link_id
        self.napp.controller.links = {link_id: mock_link}
        mock_get_link_or_create.return_value = mock_link

        link_attrs_fail = {
            'enabled': True,
            'id': link_id,
            'metadata': {},
            'endpoint_a': {
                'id': f"{dpid_a}:999",
            },
            'endpoint_b': {
                'id': f"{dpid_b}:999",
            }
        }
        with pytest.raises(RestoreError):
            self.napp._load_links({link_id: link_attrs_fail})

        link_attrs_fail = {
            'enabled': True,
            'id': link_id,
            'endpoint_a': {
                'id': f"{dpid_a}:1",
            },
            'endpoint_b': {
                'id': f"{dpid_b}:1",
            }
        }
        with pytest.raises(RestoreError):
            self.napp._load_links({link_id: link_attrs_fail})

    @patch('napps.kytos.topology.main.Main.notify_switch_links_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_enable_switch(self, mock_notify_topo, mock_sw_l_status):
        """Test enable_switch."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}

        endpoint = f"{self.base_endpoint}/switches/{dpid}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_switch.enable.call_count == 1
        self.napp.topo_controller.enable_switch.assert_called_once_with(dpid)
        mock_notify_topo.assert_called()
        mock_sw_l_status.assert_called()

        # fail case
        mock_switch.enable.call_count = 0
        dpid = "00:00:00:00:00:00:00:02"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404
        assert mock_switch.enable.call_count == 0

    @patch('napps.kytos.topology.main.Main.notify_link_enabled_state')
    @patch('napps.kytos.topology.main.Main.notify_switch_links_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_disable_switch(self, *args):
        """Test disable_switch."""
        mock_notify_topo, mock_sw_l_status, mock_noti_link = args
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        interface = Mock()
        interface.link.is_enabled = lambda: True
        interface.lock = MagicMock()
        interface.link.lock = MagicMock()
        mock_switch.interfaces = {1: interface}
        self.napp.controller.switches = {dpid: mock_switch}

        endpoint = f"{self.base_endpoint}/switches/{dpid}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_switch.disable.call_count == 1
        assert mock_noti_link.call_count == 1
        assert mock_noti_link.call_args[0][0] == interface.link
        assert mock_noti_link.call_args[0][1] == "disabled"
        assert interface.link.disable.call_count == 1
        assert self.napp.topo_controller.bulk_disable_links.call_count == 1
        self.napp.topo_controller.disable_switch.assert_called_once_with(dpid)
        mock_notify_topo.assert_called()
        mock_sw_l_status.assert_called()

        # fail case
        mock_switch.disable.call_count = 0
        dpid = "00:00:00:00:00:00:00:02"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404
        assert mock_switch.disable.call_count == 0

    async def test_get_switch_metadata(self):
        """Test get_switch_metadata."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        mock_switch.metadata = "A"
        self.napp.controller.switches = {dpid: mock_switch}

        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == {"metadata": mock_switch.metadata}

        # fail case
        dpid = "00:00:00:00:00:00:00:02"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    async def test_add_switch_metadata(
        self, mock_metadata_changes
    ):
        """Test add_switch_metadata."""
        self.napp.controller.loop = asyncio.get_running_loop()
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}
        payload = {"data": "A"}

        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 201

        mock_metadata_changes.assert_called()
        self.napp.topo_controller.add_switch_metadata.assert_called_once_with(
            dpid, payload
        )

        # fail case
        dpid = "00:00:00:00:00:00:00:02"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 404

    async def test_add_switch_metadata_wrong_format(self):
        """Test add_switch_metadata_wrong_format."""
        self.napp.controller.loop = asyncio.get_running_loop()
        dpid = "00:00:00:00:00:00:00:01"
        payload = 'A'

        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 400

        payload = None
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 415

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    async def test_delete_switch_metadata(
        self, mock_metadata_changes
    ):
        """Test delete_switch_metadata."""
        self.napp.controller.loop = asyncio.get_running_loop()
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        mock_switch.metadata = {"A": "A"}
        self.napp.controller.switches = {dpid: mock_switch}

        key = "A"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata/{key}"
        response = await self.api_client.delete(endpoint)

        assert response.status_code == 200
        assert mock_metadata_changes.call_count == 1
        del_key_mock = self.napp.topo_controller.delete_switch_metadata_key
        del_key_mock.assert_called_with(
            dpid, key
        )

        # 404, Metadata not found
        mock_switch.metadata = {}
        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata/{key}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404

        # 404, Switch not found
        key = "A"
        dpid = "00:00:00:00:00:00:00:02"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata/{key}"
        response = await self.api_client.delete(endpoint)
        assert mock_metadata_changes.call_count == 1
        assert response.status_code == 404

    # pylint: disable=too-many-statements
    @patch('napps.kytos.topology.main.Main.notify_interface_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_enable_interfaces(self, *args):
        """Test enable_interfaces."""
        (mock_notify_topo, mock_notify_interface) = args
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface_1 = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_1.link = Mock()
        mock_interface_1.link.lock = MagicMock()
        mock_interface_1.link._enabled = True
        mock_interface_2 = get_interface_mock('s1-eth2', 2, mock_switch)
        mock_interface_2.link = Mock()
        mock_interface_2.link.lock = MagicMock()
        mock_interface_2.link._enabled = False
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}

        # Switch not found
        interface_id = '00:00:00:00:00:00:00:01:1'
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404

        # Switch not enabled
        mock_switch.is_enabled = lambda: False
        self.napp.controller.switches = {dpid: mock_switch}
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 409

        # Success
        mock_switch.is_enabled = lambda: True
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 200
        assert mock_interface_1.enable.call_count == 1
        assert mock_interface_2.enable.call_count == 0
        self.napp.topo_controller.enable_interface.assert_called_with(
            interface_id
        )
        mock_notify_topo.assert_called()
        assert mock_notify_interface.call_count == 1
        assert mock_notify_interface.call_args[0][1] == 'enabled'

        mock_interface_1.enable.call_count = 0
        mock_interface_2.enable.call_count = 0
        endpoint = f"{self.base_endpoint}/interfaces/switch/{dpid}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 200
        self.napp.topo_controller.upsert_switch.assert_called_with(
            mock_switch.id, mock_switch.as_dict()
        )
        assert mock_interface_1.enable.call_count == 1
        assert mock_interface_2.enable.call_count == 1
        assert mock_notify_interface.call_count == 3
        assert mock_notify_interface.call_args[0][1] == 'enabled'

        # test interface not found
        interface_id = '00:00:00:00:00:00:00:01:3'
        mock_interface_1.enable.call_count = 0
        mock_interface_2.enable.call_count = 0
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404
        assert mock_interface_1.enable.call_count == 0
        assert mock_interface_2.enable.call_count == 0

        # test switch not found
        dpid = '00:00:00:00:00:00:00:02'
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404
        assert mock_interface_1.enable.call_count == 0
        assert mock_interface_2.enable.call_count == 0

    @patch('napps.kytos.topology.main.Main.notify_interface_status')
    @patch('napps.kytos.topology.main.Main.notify_link_enabled_state')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_disable_interfaces(self, *args):
        """Test disable_interfaces."""
        (mock_notify_topo, mock_noti_link, mock_notify_interface) = args
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface_1 = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_1.link = Mock()
        mock_interface_1.link.is_enabled = lambda: True
        mock_interface_1.link.lock = MagicMock()
        mock_interface_2 = get_interface_mock('s1-eth2', 2, mock_switch)
        mock_interface_2.link = Mock()
        mock_interface_2.link.is_enabled = lambda: False
        mock_interface_2.link.lock = MagicMock()
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}
        self.napp.controller.switches = {dpid: mock_switch}

        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 200

        self.napp.topo_controller.disable_interface.assert_called_with(
            interface_id
        )
        assert mock_interface_1.disable.call_count == 1
        assert mock_interface_2.disable.call_count == 0
        assert mock_interface_1.link.disable.call_count == 1
        assert mock_noti_link.call_count == 1
        assert mock_noti_link.call_args[0][0] == mock_interface_1.link
        assert mock_noti_link.call_args[0][1] == "disabled"
        assert self.napp.topo_controller.disable_interface.call_count == 1
        assert mock_notify_interface.call_count == 1
        assert mock_notify_interface.call_args[0][1] == 'disabled'
        mock_notify_topo.assert_called()

        mock_interface_1.disable.call_count = 0
        mock_interface_2.disable.call_count = 0

        endpoint = f"{self.base_endpoint}/interfaces/switch/{dpid}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 200

        self.napp.topo_controller.upsert_switch.assert_called_with(
            mock_switch.id, mock_switch.as_dict()
        )
        assert mock_interface_1.disable.call_count == 1
        assert mock_interface_1.link.disable.call_count == 2
        assert mock_interface_2.disable.call_count == 1
        assert mock_noti_link.call_count == 2
        assert mock_noti_link.call_args[0][0] == mock_interface_1.link
        assert mock_noti_link.call_args[0][1] == "disabled"
        bulk_controller = self.napp.topo_controller.bulk_disable_links
        assert bulk_controller.call_count == 2
        assert len(bulk_controller.call_args[0][0]) == 1
        assert mock_notify_interface.call_count == 3
        assert mock_notify_interface.call_args[0][1] == 'disabled'

        # test interface not found
        interface_id = '00:00:00:00:00:00:00:01:3'
        mock_interface_1.disable.call_count = 0
        mock_interface_2.disable.call_count = 0
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/disable"
        response = await self.api_client.post(endpoint)

        assert response.status_code == 404
        assert mock_interface_1.disable.call_count == 0
        assert mock_interface_2.disable.call_count == 0

        # test switch not found
        dpid = '00:00:00:00:00:00:00:02'
        endpoint = f"{self.base_endpoint}/interfaces/switch/{dpid}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404
        assert mock_interface_1.disable.call_count == 0
        assert mock_interface_2.disable.call_count == 0

    async def test_get_interface_metadata(self):
        """Test get_interface_metada."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.metadata = {"A": "B"}
        mock_switch.interfaces = {1: mock_interface}
        self.napp.controller.switches = {dpid: mock_switch}

        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == {"metadata": mock_interface.metadata}

        # fail case switch not found
        interface_id = '00:00:00:00:00:00:00:02:1'
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 404

        # fail case interface not found
        interface_id = '00:00:00:00:00:00:00:01:2'
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    async def test_add_interface_metadata(
        self, mock_metadata_changes
    ):
        """Test add_interface_metadata."""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.metadata = {"metada": "A"}
        mock_switch.interfaces = {1: mock_interface}
        self.napp.controller.switches = {dpid: mock_switch}
        payload = {"metada": "A"}
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 201
        mock_metadata_changes.assert_called()

        # fail case switch not found
        interface_id = '00:00:00:00:00:00:00:02:1'
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 404

        # fail case interface not found
        interface_id = '00:00:00:00:00:00:00:01:2'
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 404

    async def test_add_interface_metadata_wrong_format(self):
        """Test add_interface_metadata_wrong_format."""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = "00:00:00:00:00:00:00:01:1"
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.post(endpoint, json='A')
        assert response.status_code == 400
        response = await self.api_client.post(endpoint, json=None)
        assert response.status_code == 415

    async def test_delete_interface_metadata(self):
        """Test delete_interface_metadata."""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.remove_metadata.side_effect = [True, False]
        mock_interface.metadata = {"A": "A"}
        mock_switch.interfaces = {1: mock_interface}
        self.napp.controller.switches = {'00:00:00:00:00:00:00:01':
                                         mock_switch}

        key = 'A'
        url = f"{self.base_endpoint}/interfaces/{interface_id}/metadata/{key}"
        response = await self.api_client.delete(url)
        assert response.status_code == 200

        del_key_mock = self.napp.topo_controller.delete_interface_metadata_key
        del_key_mock.assert_called_once_with(interface_id, key)

        # fail case switch not found
        key = 'A'
        interface_id = '00:00:00:00:00:00:00:02:1'
        url = f"{self.base_endpoint}/interfaces/{interface_id}/metadata/{key}"
        response = await self.api_client.delete(url)
        assert response.status_code == 404

        # fail case interface not found
        key = 'A'
        interface_id = '00:00:00:00:00:00:00:01:2'
        url = f"{self.base_endpoint}/interfaces/{interface_id}/metadata/{key}"
        response = await self.api_client.delete(url)
        assert response.status_code == 404

        # fail case metadata not found
        key = 'B'
        interface_id = '00:00:00:00:00:00:00:01:1'
        url = f"{self.base_endpoint}/interfaces/{interface_id}/metadata/{key}"
        response = await self.api_client.delete(url)
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_link_enabled_state')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_enable_link(self, mock_notify_topo, mock_noti_link):
        """Test enable_link."""
        mock_link = MagicMock(Link)
        mock_link.lock = MagicMock()
        link_id = "1"
        mock_link.id = link_id
        mock_link.is_enabled = lambda: False
        mock_link.endpoint_a = MagicMock(is_enabled=lambda: True)
        mock_link.endpoint_b = MagicMock(is_enabled=lambda: True)
        self.napp.controller.links = {'1': mock_link}

        # 409, endpoint is/are disabled
        mock_link.endpoint_a.is_enabled = lambda: False
        mock_link.endpoint_b.is_enabled = lambda: False
        endpoint = f"{self.base_endpoint}/links/{link_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 409

        mock_link.endpoint_a.is_enabled = lambda: True
        endpoint = f"{self.base_endpoint}/links/{link_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 409

        # Success
        mock_link.endpoint_b.is_enabled = lambda: True
        endpoint = f"{self.base_endpoint}/links/{link_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_noti_link.call_count == 1
        assert mock_noti_link.call_args[0][0] == mock_link
        assert mock_noti_link.call_args[0][1] == "enabled"
        mock_notify_topo.assert_called()

        # 404, link not found
        link_id = "2"
        endpoint = f"{self.base_endpoint}/links/{link_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404
        assert mock_noti_link.call_count == 1

    @patch('napps.kytos.topology.main.Main.notify_link_enabled_state')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_disable_link(self, mock_notify_topo, mock_notify):
        """Test disable_link."""
        mock_link = MagicMock(Link)
        mock_link.lock = MagicMock()
        mock_link.is_enabled = lambda: True
        self.napp.controller.links = {'1': mock_link}

        link_id = "1"
        endpoint = f"{self.base_endpoint}/links/{link_id}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_notify_topo.call_count == 1
        assert mock_notify.call_count == 1
        assert mock_notify.call_args[0][0] == mock_link
        assert mock_notify.call_args[0][1] == "disabled"
        assert mock_link.disable.call_count == 1
        assert self.napp.topo_controller.disable_link.call_count == 1

        # fail case
        link_id = "2"
        endpoint = f"{self.base_endpoint}/links/{link_id}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404

    def test_handle_lldp_status_updated(self):
        """Test handle_lldp_status_updated."""
        event = MagicMock()
        self.napp.controller.buffers.app.put = MagicMock()

        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_b = "00:00:00:00:00:00:00:02"
        dpids = [dpid_a, dpid_b]
        interface_ids = [f"{dpid}:1" for dpid in dpids]

        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_switch_b = get_switch_mock(dpid_b, 0x04)
        self.napp.controller.switches = {dpid_a: mock_switch_a,
                                         dpid_b: mock_switch_b}

        event.content = {"interface_ids": interface_ids, "state": "disabled"}
        self.napp.handle_lldp_status_updated(event)

        mock_put = self.napp.controller.buffers.app.put
        assert mock_put.call_count == len(interface_ids)

    def test_handle_topo_controller_upsert_switch(self):
        """Test handle_topo_controller_upsert_switch."""
        event = MagicMock()
        self.napp.handle_topo_controller_upsert_switch(event)
        mock = self.napp.topo_controller.upsert_switch
        mock.assert_called_with(event.id, event.as_dict())

    async def test_get_link_metadata(self):
        """Test get_link_metadata."""
        mock_link = MagicMock(Link)
        mock_link.lock = MagicMock()
        mock_link.metadata = "A"
        self.napp.controller.links = {'1': mock_link}
        msg_success = {"metadata": "A"}

        link_id = "1"
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 200
        assert msg_success == response.json()

        # fail case
        link_id = "2"
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    async def test_add_link_metadata(
        self,
        mock_metadata_changes,
        mock_topology_update
    ):
        """Test add_link_metadata."""
        self.napp.controller.loop = asyncio.get_running_loop()
        mock_link = MagicMock(Link)
        mock_link.lock = MagicMock()
        mock_link.metadata = "A"
        self.napp.controller.links = {'1': mock_link}
        payload = {"metadata": "A"}
        link_id = 1

        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 201
        mock_metadata_changes.assert_called()
        mock_topology_update.assert_called()

        # fail case
        link_id = 2
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 404

    async def test_add_link_metadata_wrong_format(self):
        """Test add_link_metadata_wrong_format."""
        self.napp.controller.loop = asyncio.get_running_loop()
        link_id = 'cf0f4071be426b3f745027f5d22'
        payload = "A"
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata"
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 400

        payload = None
        response = await self.api_client.post(endpoint, json=payload)
        assert response.status_code == 415

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    async def test_delete_link_metadata(
        self,
        mock_metadata_changes,
        mock_topology_update
    ):
        """Test delete_link_metadata."""
        mock_link = MagicMock(Link)
        mock_link.lock = MagicMock()
        mock_link.metadata = {"A": "A"}
        mock_link.remove_metadata.side_effect = [True, False]
        self.napp.controller.links = {'1': mock_link}

        link_id = 1
        key = 'A'
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata/{key}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 200
        del_mock = self.napp.topo_controller.delete_link_metadata_key
        del_mock.assert_called_once_with(mock_link.id, key)
        mock_metadata_changes.assert_called()
        mock_topology_update.assert_called()

        # fail case link not found
        link_id = 2
        key = 'A'
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata/{key}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404

        # fail case metadata not found
        link_id = 1
        key = 'B'
        endpoint = f"{self.base_endpoint}/links/{link_id}/metadata/{key}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_new_switch(self, mock_notify_topology_update):
        """Test handle_new_switch."""
        mock_event = MagicMock()
        mock_switch = create_autospec(Switch)
        mock_event.content['switch'] = mock_switch
        self.napp.handle_new_switch(mock_event)
        mock = self.napp.topo_controller.upsert_switch
        mock.assert_called_once_with(mock_event.content['switch'].id,
                                     mock_event.content['switch'].as_dict())
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_connection_lost(self, mock_notify_topology_update):
        """Test handle connection_lost."""
        mock_event = MagicMock()
        mock_switch = create_autospec(Switch)
        mock_switch.return_value = True
        mock_event.content['source'] = mock_switch
        self.napp.handle_connection_lost(mock_event)
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_link_down')
    @patch('napps.kytos.topology.main.Main.handle_interface_link_up')
    def test_handle_interface_created(self, mock_link_up, mock_link_down):
        """Test handle_interface_created."""
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        mock_interface.lock = MagicMock()
        mock_event.content = {'interface': mock_interface}
        self.napp.handle_interface_created(mock_event)
        mock_link_up.assert_called()
        mock_link_down.assert_not_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_link_down')
    @patch('napps.kytos.topology.main.Main.handle_interface_link_up')
    def test_handle_interface_created_inactive(self, mock_link_up,
                                               mock_link_down):
        """Test handle_interface_created inactive."""
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        mock_interface.lock = MagicMock()
        mock_event.content = {'interface': mock_interface}
        mock_interface.is_active.return_value = False
        self.napp.handle_interface_created(mock_event)
        mock_link_up.assert_not_called()
        mock_link_down.assert_called()

    def test_handle_interfaces_created(self):
        """Test handle_interfaces_created."""
        buffers_app_mock = MagicMock()
        self.napp.controller.buffers.app = buffers_app_mock
        mock_switch = create_autospec(Switch)
        mock_switch.lock = MagicMock()
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        mock_interface.lock = MagicMock()
        mock_interface.switch = mock_switch
        mock_interface_two = create_autospec(Interface)
        mock_interface_two.id = "2"
        mock_interface_two.lock = MagicMock()
        mock_event.content = {'interfaces': [mock_interface,
                              mock_interface_two]}
        self.napp.handle_interfaces_created(mock_event)
        upsert_mock = self.napp.topo_controller.upsert_switch
        upsert_mock.assert_called_with(mock_switch.id, mock_switch.as_dict())
        assert self.napp.controller.buffers.app.put.call_count == 2

    @patch('napps.kytos.topology.main.Main.handle_interface_link_down')
    def test_handle_interface_down(self, mock_handle_interface_link_down):
        """Test handle interface down."""
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_down(mock_event)
        mock_handle_interface_link_down.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_down')
    def test_interface_deleted(self, mock_handle_interface_link_down):
        """Test interface deleted."""
        mock_event = MagicMock()
        self.napp.handle_interface_deleted(mock_event)
        mock_handle_interface_link_down.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_interface_link_up(self, mock_notify_topology_update):
        """Test interface link_up."""
        self.napp.controller.buffers.app.put = MagicMock()

        tnow = time.time()
        mock_switch_a = create_autospec(Switch)
        mock_switch_a.is_active.return_value = True
        mock_switch_b = create_autospec(Switch)
        mock_switch_b.is_active.return_value = True
        mock_interface_a = create_autospec(Interface)
        mock_interface_a.switch = mock_switch_a
        mock_interface_a.is_active.return_value = False
        mock_interface_b = create_autospec(Interface)
        mock_interface_b.switch = mock_switch_b
        mock_interface_b.is_active.return_value = True
        mock_link = create_autospec(Link)
        mock_link.lock = MagicMock()
        mock_link.get_metadata.return_value = tnow
        mock_link.is_active.return_value = False
        mock_link.endpoint_a = mock_interface_a
        mock_link.endpoint_b = mock_interface_b
        mock_link.status = EntityStatus.UP
        mock_interface_a.link = mock_link
        mock_interface_b.link = mock_link
        event = KytosEvent("kytos.of_core.switch.interface.down")
        self.napp.handle_interface_link_up(mock_interface_a, event)
        mock_notify_topology_update.assert_called()
        assert mock_link.id in self.napp.link_status_change
        mock_link.activate.assert_called()
        self.napp.controller.buffers.app.put.assert_not_called()

        mock_interface_a.is_active.return_value = True
        event = KytosEvent("kytos.of_core.switch.interface.down")
        self.napp.handle_interface_link_up(mock_interface_a, event)

        assert mock_link.id in self.napp.link_status_change
        link_status_info = self.napp.link_status_change[mock_link.id]
        mock_link.activate.assert_called()
        assert self.napp.controller.buffers.app.put.call_count == 1
        ev = "kytos/topology.notify_link_up_if_status"
        assert self.napp.controller.buffers.app.put.call_args[0][0].name == ev

        mock_link.is_active.return_value = True
        orig_change_time = link_status_info["last_status_change"]

        self.napp.handle_interface_link_up(mock_interface_a, event)

        link_status_info = self.napp.link_status_change[mock_link.id]
        new_change_time = link_status_info["last_status_change"]
        assert orig_change_time == new_change_time

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_down(self, *args):
        """Test interface link down."""
        mock_status_change, mock_topology_update = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.lock = MagicMock()
        mock_link.is_active.return_value = True
        mock_interface.link = mock_link
        event = KytosEvent("kytos.of_core.switch.interface.link_up")
        self.napp.handle_interface_link_down(mock_interface, event)
        mock_topology_update.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_down_unordered_event(self, *args):
        """Test interface link down unordered event."""
        (mock_status_change, mock_topology_update) = args

        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        event_2 = KytosEvent("kytos.of_core.switch.interface.down")
        event_1 = KytosEvent("kytos.of_core.switch.interface.up")
        assert event_1.timestamp > event_2.timestamp
        self.napp._intfs_updated_at[mock_interface.id] = event_1.timestamp
        self.napp.handle_interface_link_down(mock_interface, event_2)
        mock_topology_update.assert_not_called()
        mock_status_change.assert_not_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_up_unordered_event(self, *args):
        """Test interface link up unordered event."""
        (mock_status_change, mock_topology_update) = args

        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        event_2 = KytosEvent("kytos.of_core.switch.interface.up")
        event_1 = KytosEvent("kytos.of_core.switch.interface.down")
        assert event_1.timestamp > event_2.timestamp
        self.napp._intfs_updated_at[mock_interface.id] = event_1.timestamp
        self.napp.handle_interface_link_up(mock_interface, event_2)
        mock_topology_update.assert_not_called()
        mock_status_change.assert_not_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_down(self, *args):
        """Test interface link down."""
        (mock_status_change, mock_topology_update) = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.lock = MagicMock()
        mock_link.is_active.return_value = True
        mock_interface.link = mock_link
        self.napp.handle_link_down(mock_interface)
        mock_interface.deactivate.assert_not_called()
        mock_link.deactivate.assert_called()
        assert mock_topology_update.call_count == 1
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_link_down_not_active(self, args):
        """Test interface link down with link not active."""
        mock_topology_update = args
        self.napp.controller.buffers.app.put = MagicMock()

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.lock = MagicMock()
        mock_link.is_active.return_value = False
        mock_link.get_metadata.return_value = False
        mock_interface.link = mock_link
        self.napp.link_up = set()
        self.napp.link_status_change[mock_link.id] = {}
        self.napp.handle_link_down(mock_interface)
        mock_topology_update.assert_called()
        self.napp.controller.buffers.app.put.assert_not_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_down_not_active_last_status(self, *args):
        """Test interface link down with link not active."""
        (mock_status_change, mock_topology_update) = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.lock = MagicMock()
        mock_link.is_active.return_value = False
        mock_link.get_metadata.return_value = True
        mock_interface.link = mock_link
        self.napp.handle_link_down(mock_interface)
        mock_topology_update.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_link_up(self, mock_notify_topology_update):
        """Test handle link up."""
        mock_switch_a = create_autospec(Switch)
        mock_switch_a.is_active.return_value = True
        mock_interface = create_autospec(Interface)
        mock_interface.switch = mock_switch_a
        mock_interface.is_active.return_value = True
        mock_link = MagicMock(status=EntityStatus.UP)
        mock_link.is_active.return_value = True
        mock_interface.link = mock_link
        self.napp.handle_link_up(mock_interface)
        mock_interface.activate.assert_not_called()
        mock_notify_topology_update.assert_called()
        assert self.napp.controller.buffers.app.put.call_count == 2
        ev = "kytos/topology.notify_link_up_if_status"
        assert self.napp.controller.buffers.app.put.call_args[0][0].name == ev

    @patch('time.sleep')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_up_intf_down(self, *args):
        """Test handle link up but one intf down."""
        (mock_status_change, mock_topology_update, _) = args

        mock_switch = create_autospec(Switch)
        mock_interface = create_autospec(Interface)
        mock_interface.switch = mock_switch
        mock_link = MagicMock()
        mock_link.endpoint_a.is_active.return_value = False
        mock_link.is_active.return_value = False
        mock_interface.link = mock_link
        self.napp.handle_link_up(mock_interface)
        mock_interface.activate.assert_not_called()
        assert mock_topology_update.call_count == 1
        mock_status_change.assert_not_called()

    @patch('napps.kytos.topology.main.Main.notify_link_up_if_status')
    def test_add_links(self, mock_notify_link_up_if_status):
        """Test add_links."""
        mock_link = MagicMock()
        self.napp.controller.get_link_or_create = MagicMock()
        mock_get_link_or_create = self.napp.controller.get_link_or_create
        mock_get_link_or_create.return_value = (mock_link, True)
        mock_event = MagicMock()
        mock_intf_a = MagicMock()
        mock_intf_b = MagicMock()
        mock_event.content = {
            "interface_a": mock_intf_a,
            "interface_b": mock_intf_b
        }
        self.napp.add_links(mock_event)
        assert mock_link.id in self.napp.link_status_change
        mock_get_link_or_create.assert_called()
        mock_notify_link_up_if_status.assert_called()

    def test_notify_switch_enabled(self):
        """Test notify switch enabled."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        self.napp.notify_switch_enabled(dpid)
        mock_buffers_put.assert_called()

    def test_notify_switch_disabled(self):
        """Test notify switch disabled."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        self.napp.notify_switch_disabled(dpid)
        mock_buffers_put.assert_called()

    def test_notify_topology_update(self):
        """Test notify_topology_update."""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        self.napp.notify_topology_update()
        mock_buffers_put.assert_called()

    def test_notify_link_status_change(self):
        """Test notify link status change."""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        mock_link = create_autospec(Link)
        mock_link.id = 'test_link'
        mock_link.status_reason = frozenset()
        mock_link.status = EntityStatus.UP

        # Check when switching to up
        self.napp.notify_link_status_change(mock_link, 'test')
        assert mock_buffers_put.call_count == 1
        args, _ = mock_buffers_put.call_args
        event = args[0]
        assert event.content['link'] is mock_link
        assert event.content['reason'] == 'test'
        assert event.name == 'kytos/topology.link_up'

        # Check result when no change
        self.napp.notify_link_status_change(mock_link, 'test2')
        assert mock_buffers_put.call_count == 1

        # Check when switching to down
        mock_link.status_reason = frozenset({'disabled'})
        mock_link.status = EntityStatus.DOWN
        self.napp.notify_link_status_change(mock_link, 'test3')
        assert mock_buffers_put.call_count == 2
        args, _ = mock_buffers_put.call_args
        event = args[0]
        assert event.content['link'] is mock_link
        assert event.content['reason'] == 'test3'
        assert event.name == 'kytos/topology.link_down'

    def test_notify_metadata_changes(self):
        """Test notify metadata changes."""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        count = 0
        for spec in [Switch, Interface, Link]:
            mock_obj = create_autospec(spec)
            mock_obj.metadata = {"some_key": "some_value"}
            self.napp.notify_metadata_changes(mock_obj, 'added')
            assert mock_buffers_put.call_count == count+1
            count += 1
        with pytest.raises(ValueError):
            self.napp.notify_metadata_changes(MagicMock(), 'added')

    def test_notify_port_created(self):
        """Test notify port created."""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        event = KytosEvent("some_event")
        expected_name = "kytos/topology.port.created"
        self.napp.notify_port_created(event)
        assert mock_buffers_put.call_count == 1
        assert mock_buffers_put.call_args_list[0][0][0].name == expected_name

    def test_handle_link_liveness_disabled(self) -> None:
        """Test handle_link_liveness_disabled."""
        interfaces = [MagicMock(id=f"intf{n}") for n in range(4)]
        links = {
            "link1": MagicMock(id="link1",
                               endpoint_a=interfaces[0],
                               endpoint_b=interfaces[1]),
            "link2": MagicMock(id="link2",
                               endpoint_a=interfaces[2],
                               endpoint_b=interfaces[3]),
        }
        interfaces[0].link = links["link1"]
        interfaces[1].link = links["link1"]
        interfaces[2].link = links["link2"]
        interfaces[3].link = links["link2"]
        self.napp.controller.links = links
        self.napp.notify_topology_update = MagicMock()
        self.napp.notify_link_status_change = MagicMock()

        self.napp.handle_link_liveness_disabled(interfaces)

        assert self.napp.notify_topology_update.call_count == 1
        assert self.napp.notify_link_status_change.call_count == len(links)

    def test_link_status_hook_link_up_timer(self) -> None:
        """Test status hook link up timer."""
        last_change = time.time() - self.napp.link_up_timer + 5
        link = MagicMock(metadata={"last_status_change": last_change})
        self.napp.link_status_change[link.id] = {
            "last_status_change": last_change,
        }
        link.is_active.return_value = True
        link.is_enabled.return_value = True
        res = self.napp.link_status_hook_link_up_timer(link)
        assert res == EntityStatus.DOWN

        last_change = time.time() - self.napp.link_up_timer
        self.napp.link_status_change[link.id] = {
            "last_status_change": last_change,
        }
        res = self.napp.link_status_hook_link_up_timer(link)
        assert res is None

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('time.sleep')
    def test_notify_link_up_if_status(
        self,
        mock_sleep,
        mock_notify_topo,
        mock_notify_link,
    ) -> None:
        """Test notify link up if status."""

        link = MagicMock(status=EntityStatus.UP)
        self.napp.link_status_change[link.id] = {
            "notified_up_at": now(),
        }
        assert not self.napp.notify_link_up_if_status(link, "link up")
        link.update_metadata.assert_not_called()
        mock_notify_topo.assert_not_called()
        mock_notify_link.assert_not_called()

        link = MagicMock(status=EntityStatus.UP)
        orig_time = now() - timedelta(seconds=60)
        self.napp.link_status_change[link.id] = {
            "notified_up_at": orig_time,
        }
        assert not self.napp.notify_link_up_if_status(link, "link up")
        link_status_info = self.napp.link_status_change[link.id]
        new_time = link_status_info["notified_up_at"]
        assert new_time != orig_time
        mock_notify_topo.assert_called()
        mock_notify_link.assert_called()

        assert mock_sleep.call_count == 2

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_notify_switch_links_status(self, mock_notify_link_status_change):
        """Test switch links notification when switch status change"""
        buffers_app_mock = MagicMock()
        self.napp.controller.buffers.app = buffers_app_mock
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        mock_interface = MagicMock()
        mock_interface.switch = mock_switch
        mock_switch.interfaces = {
            1: mock_interface
        }
        link1 = MagicMock()
        link1.endpoint_a = mock_interface
        mock_interface.link = link1
        self.napp.controller.links = {1: link1}

        self.napp.notify_switch_links_status(mock_switch, "link enabled")
        assert self.napp.controller.buffers.app.put.call_count == 1

        self.napp.notify_switch_links_status(mock_switch, "link disabled")
        assert self.napp.controller.buffers.app.put.call_count == 1
        assert mock_notify_link_status_change.call_count == 1

        # Without notification
        link1.endpoint_a = None
        mock_interface.link = None
        self.napp.notify_switch_links_status(mock_switch, "link enabled")
        assert self.napp.controller.buffers.app.put.call_count == 1

    @patch('napps.kytos.topology.main.Main.notify_interface_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interruption_start(
        self,
        mock_notify_link_status_change,
        mock_notify_topology_update,
        mock_notify_interface_status,
    ):
        """Tests processing of received interruption start events."""
        link_a = MagicMock()
        link_b = MagicMock()
        link_c = MagicMock()
        self.napp.controller.links = {
            'link_a': link_a,
            'link_b': link_b,
            'link_c': link_c,
        }
        mock_get_interface = MagicMock(side_effect=[Mock(), Mock()])
        self.napp.controller.get_interface_by_id = mock_get_interface
        event = KytosEvent(
            "topology.interruption.start",
            {
                'type': 'test_interruption',
                'switches': [
                ],
                'interfaces': [
                    'intf_a',
                    'intf_b',
                ],
                'links': [
                    'link_a',
                    'link_c',
                ],
            }
        )
        self.napp.handle_interruption_start(event)
        mock_notify_link_status_change.assert_has_calls(
            [
                call(link_a, 'test_interruption'),
                call(link_c, 'test_interruption'),
            ]
        )
        assert mock_notify_link_status_change.call_count == 2
        mock_notify_topology_update.assert_called_once()
        assert mock_notify_interface_status.call_count == 2

    @patch('napps.kytos.topology.main.Main.notify_interface_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interruption_end(
        self,
        mock_notify_link_status_change,
        mock_notify_topology_update,
        mock_notify_interface_status,
    ):
        """Tests processing of received interruption end events."""
        link_a = MagicMock()
        link_b = MagicMock()
        link_c = MagicMock()
        self.napp.controller.links = {
            'link_a': link_a,
            'link_b': link_b,
            'link_c': link_c,
        }
        mock_get_interface = MagicMock(side_effect=[Mock(), Mock()])
        self.napp.controller.get_interface_by_id = mock_get_interface
        event = KytosEvent(
            "topology.interruption.start",
            {
                'type': 'test_interruption',
                'switches': [
                ],
                'interfaces': [
                    'intf_a',
                    'intf_b',
                ],
                'links': [
                    'link_a',
                    'link_c',
                ],
            }
        )
        self.napp.handle_interruption_end(event)
        mock_notify_link_status_change.assert_has_calls(
            [
                call(link_a, 'test_interruption'),
                call(link_c, 'test_interruption'),
            ]
        )
        assert mock_notify_link_status_change.call_count == 2
        mock_notify_topology_update.assert_called_once()
        assert mock_notify_interface_status.call_count == 2

    async def test_set_tag_range(self):
        """Test set_tag_range"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.set_tag_ranges = MagicMock()
        mock_interface.link = None
        self.napp.handle_on_interface_tags = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        payload = {
            "tag_type": "vlan",
            "tag_ranges": [[20, 20], [200, 3000]]
        }
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 200

        args = mock_interface.set_tag_ranges.call_args[0]
        assert args[0] == payload['tag_type']
        assert args[1] == payload['tag_ranges']
        assert self.napp.handle_on_interface_tags.call_count == 1

    async def test_set_tag_range_not_found(self):
        """Test set_tag_range. Not found"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = None
        payload = {
            "tag_type": "vlan",
            "tag_ranges": [[20, 20], [200, 3000]]
        }
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 404

    async def test_set_tag_range_tag_error(self):
        """Test set_tag_range TagRangeError"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.set_tag_ranges = MagicMock()
        mock_interface.set_tag_ranges.side_effect = KytosSetTagRangeError("")
        mock_interface.notify_interface_tags = MagicMock()
        mock_interface.link = None
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        payload = {
            "tag_type": "vlan",
            "tag_ranges": [[20, 20], [200, 3000]]
        }
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 400
        assert mock_interface.notify_interface_tags.call_count == 0

    async def test_set_tag_range_type_error(self):
        """Test set_tag_range TagRangeError"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.set_tag_ranges = MagicMock()
        mock_interface.set_tag_ranges.side_effect = KytosTagtypeNotSupported(
            ""
        )
        self.napp.handle_on_interface_tags = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        payload = {
            "tag_type": "wrong_tag_type",
            "tag_ranges": [[20, 20], [200, 3000]]
        }
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 400
        assert self.napp.handle_on_interface_tags.call_count == 0

    async def test_delete_tag_range(self):
        """Test delete_tag_range"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.reset_tag_ranges = MagicMock()
        self.napp.handle_on_interface_tags = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.delete(url)
        assert response.status_code == 200
        assert mock_interface.reset_tag_ranges.call_count == 1

    async def test_delete_tag_range_not_found(self):
        """Test delete_tag_range. Not found"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.reset_tag_ranges = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = None
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.delete(url)
        assert response.status_code == 404
        assert mock_interface.reset_tag_ranges.call_count == 0

    async def test_delete_tag_range_type_error(self):
        """Test delete_tag_range TagRangeError"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.reset_tag_ranges = MagicMock()
        remove_tag = mock_interface.reset_tag_ranges
        remove_tag.side_effect = KytosTagtypeNotSupported("")
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.delete(url)
        assert response.status_code == 400

    async def test_get_all_tag_ranges(self):
        """Test get_all_tag_ranges"""
        self.napp.controller.loop = asyncio.get_running_loop()
        dpid = '00:00:00:00:00:00:00:01'
        switch = get_switch_mock(dpid)
        interface = get_interface_mock('s1-eth1', 1, switch)
        tags = {'vlan': [[1, 4095]]}
        special_tags = {'vlan': ["vlan"]}
        interface.tag_ranges = tags
        interface.available_tags = tags
        interface.default_tag_ranges = tags
        interface.special_available_tags = special_tags
        interface.special_tags = special_tags
        interface.default_special_tags = special_tags
        switch.interfaces = {1: interface}
        self.napp.controller.switches = {dpid: switch}
        url = f"{self.base_endpoint}/interfaces/tag_ranges"
        response = await self.api_client.get(url)
        expected = {dpid + ":1": {
            'available_tags': tags,
            'tag_ranges': tags,
            'default_tag_ranges': tags,
            'special_available_tags': special_tags,
            'special_tags': special_tags,
            'default_special_tags': special_tags,
        }}
        assert response.status_code == 200
        assert response.json() == expected

    async def test_get_tag_ranges_by_intf(self):
        """Test get_tag_ranges_by_intf"""
        self.napp.controller.loop = asyncio.get_running_loop()
        dpid = '00:00:00:00:00:00:00:01'
        switch = get_switch_mock(dpid)
        interface = get_interface_mock('s1-eth1', 1, switch)
        tags = {'vlan': [[1, 4095]]}
        special_tags = {'vlan': ["vlan"]}
        interface.default_tag_ranges = tags
        interface.tag_ranges = tags
        interface.available_tags = tags
        interface.special_available_tags = special_tags
        interface.special_tags = special_tags
        interface.default_special_tags = special_tags
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = interface
        url = f"{self.base_endpoint}/interfaces/{dpid}:1/tag_ranges"
        response = await self.api_client.get(url)
        expected = {
            '00:00:00:00:00:00:00:01:1': {
                "available_tags": tags,
                "tag_ranges": tags,
                "default_tag_ranges": tags,
                'special_available_tags': special_tags,
                'special_tags': special_tags,
                'default_special_tags': special_tags,
            }
        }
        assert response.status_code == 200
        assert response.json() == expected

    async def test_get_tag_ranges_by_intf_error(self):
        """Test get_tag_ranges_by_intf with NotFound"""
        self.napp.controller.loop = asyncio.get_running_loop()
        dpid = '00:00:00:00:00:00:00:01'
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = None
        url = f"{self.base_endpoint}/interfaces/{dpid}:1/tag_ranges"
        response = await self.api_client.get(url)
        assert response.status_code == 404

    async def test_set_special_tags(self):
        """Test set_special_tags"""
        self.napp.controller.loop = asyncio.get_running_loop()
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_intf = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_intf.set_special_tags = MagicMock()
        self.napp.handle_on_interface_tags = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_intf
        payload = {
            "tag_type": "vlan",
            "special_tags": ["untagged"],
        }
        url = f"{self.base_endpoint}/interfaces/{interface_id}/"\
              "special_tags"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 200

        args = mock_intf.set_special_tags.call_args[0]
        assert args[0] == payload["tag_type"]
        assert args[1] == payload['special_tags']
        assert self.napp.handle_on_interface_tags.call_count == 1

        # KytosTagError
        mock_intf.set_special_tags.side_effect = KytosTagtypeNotSupported("")
        url = f"{self.base_endpoint}/interfaces/{interface_id}/"\
              "special_tags"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 400
        assert self.napp.handle_on_interface_tags.call_count == 1

        # Interface Not Found
        self.napp.controller.get_interface_by_id.return_value = None
        url = f"{self.base_endpoint}/interfaces/{interface_id}/"\
              "special_tags"
        response = await self.api_client.post(url, json=payload)
        assert response.status_code == 404
        assert self.napp.handle_on_interface_tags.call_count == 1

    async def test_delete_link(self):
        """Test delete_link"""
        dpid_a = '00:00:00:00:00:00:00:01'
        dpid_b = '00:00:00:00:00:00:00:02'
        link_id = 'mock_link'
        mock_switch_a = get_switch_mock(dpid_a)
        mock_switch_b = get_switch_mock(dpid_b)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_link = get_link_mock(mock_interface_a, mock_interface_b)
        mock_link.id = link_id
        mock_link.status = EntityStatus.DISABLED
        mock_interface_a.link = mock_link
        mock_interface_b.link = mock_link
        self.napp.controller.links = {link_id: mock_link}

        call_count = self.napp.controller.buffers.app.put.call_count
        endpoint = f"{self.base_endpoint}/links/{link_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 200
        assert self.napp.topo_controller.delete_link.call_count == 1
        assert len(self.napp.controller.links) == 0
        call_count += 2
        assert self.napp.controller.buffers.app.put.call_count == call_count

        # Link is up
        self.napp.controller.links = {link_id: mock_link}
        mock_link.status = EntityStatus.UP
        endpoint = f"{self.base_endpoint}/links/{link_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409
        assert self.napp.topo_controller.delete_link.call_count == 1
        assert self.napp.controller.buffers.app.put.call_count == call_count

        # Link does not exist
        del self.napp.controller.links[link_id]
        endpoint = f"{self.base_endpoint}/links/{link_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404
        assert self.napp.topo_controller.delete_link.call_count == 1
        assert self.napp.controller.buffers.app.put.call_count == call_count

    @patch('napps.kytos.topology.main.Main.get_flows_by_switch')
    async def test_delete_switch(self, mock_get):
        """Test delete_switch"""
        # Error 404 NotFound
        dpid = '00:00:00:00:00:00:00:01'
        endpoint = f"{self.base_endpoint}/switches/{dpid}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404, response.text

        # Error 409 Switch not disabled
        mock_switch = get_switch_mock(dpid)
        mock_switch.status = EntityStatus.UP
        self.napp.controller.switches = {dpid: mock_switch}
        endpoint = f"{self.base_endpoint}/switches/{dpid}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409, response.text

        # Error 409 Interface vlan is being used
        mock_intf = MagicMock(all_tags_available=lambda: False)
        mock_switch.interfaces = {1: mock_intf}
        mock_switch.status = EntityStatus.DISABLED
        endpoint = f"{self.base_endpoint}/switches/{dpid}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409, response.text

        # Error 409 Swith have links
        mock_switch_2 = get_switch_mock("00:00:00:00:00:00:00:02")
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_a.all_tags_available = lambda: True
        mock_switch.interfaces[1] = mock_interface_a
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_2)
        mock_link = get_link_mock(mock_interface_a, mock_interface_b)
        mock_interface_a.link = mock_link
        mock_interface_b.link = mock_link
        self.napp.controller.links = {'0e2b5d7bc858b9f38db11b69': mock_link}
        endpoint = f"{self.base_endpoint}/switches/{dpid}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409, response.text

        # Error 409 Switch has flows
        # TODO: I don't think this is testing what it thinks it is
        mock_get.return_value = {dpid: {}}
        endpoint = f"{self.base_endpoint}/switches/{dpid}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409, response.text

        # Success 202
        mock_get.return_value = {}
        self.napp.controller.links = {}
        mock_interface_a.link = None
        endpoint = f"{self.base_endpoint}/switches/{dpid}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 200, response.text

    def test_notify_link_status(self):
        """Test notify_link_enabled_state"""
        self.napp.controller.buffers.app.put.reset_mock()
        link = Mock()
        link.id = 'mock_link'
        self.napp.notify_link_enabled_state(link, 'enabled')
        assert self.napp.controller.buffers.app.put.call_count == 1

        self.napp.notify_link_enabled_state(link, 'disabled')
        assert self.napp.controller.buffers.app.put.call_count == 2

    @patch('napps.kytos.topology.main.tenacity.nap.time')
    @patch('httpx.get')
    def test_get_flows_by_switch(self, mock_get, _):
        """Test get_flows_by_switch"""
        dpid = "00:01"
        mock_get.return_value.status_code = 400
        with pytest.raises(tenacity.RetryError):
            self.napp.get_flows_by_switch(dpid)

        mock_get.return_value.status_code = 200
        mock_get.return_value.is_server_error = False
        expected = {dpid: "mocked_flows"}
        mock_get.return_value.json.return_value = expected
        actual = self.napp.get_flows_by_switch(dpid)
        assert actual == "mocked_flows"

    @patch('napps.kytos.topology.main.Main.get_intf_usage')
    @patch('napps.kytos.topology.main.Main._delete_interface')
    async def test_delete_interface_api(self, mock_delete, mock_usage):
        """Test delete interface API call"""
        switch_id = "00:00:00:00:00:00:00:01"
        intf_id = "00:00:00:00:00:00:00:01:1"

        # Error 400 Invalid interface id
        endpoint = f"{self.base_endpoint}/interfaces/{intf_id}x"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 400, response

        # Error 404 Switch not found
        endpoint = f"{self.base_endpoint}/interfaces/{intf_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404, response

        # Error 404 Interface not found
        mock_switch = get_switch_mock(switch_id)
        mock_switch.interfaces = {}
        self.napp.controller.switches = {switch_id: mock_switch}
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404, response

        # Error 409 Interface is used
        mock_switch.interfaces = {1: MagicMock()}
        self.napp.controller.switches = {switch_id: mock_switch}
        mock_usage.return_value = "It is enabled or active."
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409, response

        # Success
        mock_usage.return_value = None
        mock_delete.return_value = True
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 200, response
        assert self.napp.controller.buffers.app.put.call_count
        args = self.napp.controller.buffers.app.put.call_args_list
        event = args[-1][0][0]
        assert event.name == "kytos/topology.interface.deleted"
        assert "interface" in event.content

    def test_get_intf_usage(self):
        """Test get_intf_usage"""
        switch_id = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(switch_id)
        mock_intf = get_interface_mock('s1-eth1', 1, mock_switch)

        mock_intf.is_enabled.return_value = False
        mock_intf.is_active.return_value = True
        actual_usage = self.napp.get_intf_usage(mock_intf)
        assert actual_usage == "It is enabled or active."

        mock_intf.is_active.return_value = False
        mock_intf.link = Mock()
        actual_usage = self.napp.get_intf_usage(mock_intf)
        assert "It has a link," in actual_usage

        mock_intf.link = None
        self.napp.get_flow_id_by_intf = MagicMock(return_value="mock_flow")
        actual_usage = self.napp.get_intf_usage(mock_intf)
        assert "There is a flow installed" in actual_usage

        self.napp.get_flow_id_by_intf.return_value = None
        actual_usage = self.napp.get_intf_usage(mock_intf)
        assert actual_usage is None

    @patch('napps.kytos.topology.main.Main.get_flows_by_switch')
    def test_get_flow_id_by_intf(self, mock_flows):
        """Test get_flow_id_by_intf"""
        flows = [
            {
                "flow": {
                    "match": {"in_port": 1, "dl_vlan": 200},
                },
                "flow_id": "flow_0",
            },
            {
                "flow": {
                    "actions": [{"action_type": "output", "port": 1}]
                },
                "flow_id": "flow_1",
            },
            {
                "flow": {
                    "instructions": [{
                        "instruction_type": "apply_actions",
                        "actions": [{"action_type": "output", "port": 1}]
                    }]
                },
                "flow_id": "flow_2",
            },
            {
                "flow": {
                    "match": {"dl_src": "ee:ee:ee:ee:ee:02"},
                },
                "flow_id": "flow_3",
            }
        ]

        switch_id = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(switch_id)
        mock_intf = get_interface_mock('s1-eth1', 1, mock_switch)

        mock_flows.return_value = [flows[0]]
        flow_id = self.napp.get_flow_id_by_intf(mock_intf)
        assert flow_id == flows[0]["flow_id"]

        mock_flows.return_value = [flows[1]]
        flow_id = self.napp.get_flow_id_by_intf(mock_intf)
        assert flow_id == flows[1]["flow_id"]

        mock_flows.return_value = [flows[2]]
        flow_id = self.napp.get_flow_id_by_intf(mock_intf)
        assert flow_id == flows[2]["flow_id"]

        mock_flows.return_value = [flows[3]]
        flow_id = self.napp.get_flow_id_by_intf(mock_intf)
        assert flow_id is None

    def test_delete_interface(self):
        """Test _delete_interface"""
        switch_id = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(switch_id)
        mock_intf = get_interface_mock('s1-eth1', 1, mock_switch)
        self.napp._delete_interface(mock_intf)
        assert mock_switch.remove_interface.call_count == 1
        assert self.napp.topo_controller.upsert_switch.call_count == 1
        delete = self.napp.topo_controller.delete_interface_from_details
        assert delete.call_count == 1

    def test_detect_mismatched_link(self):
        """Test detect_mismatched_link"""
        mock_link_1 = MagicMock(id='link_1')
        mock_link_1.endpoint_a = MagicMock(link=mock_link_1)
        mock_link_1.endpoint_b = MagicMock(link=None)
        assert self.napp.detect_mismatched_link(mock_link_1)

        mock_link_1.endpoint_a.link = None
        mock_link_1.endpoint_b.link = mock_link_1
        assert self.napp.detect_mismatched_link(mock_link_1)

        mock_link_2 = MagicMock(id='link_2')
        mock_link_1.endpoint_a.link = mock_link_2
        assert self.napp.detect_mismatched_link(mock_link_1)

        mock_link_1.endpoint_a.link = mock_link_1
        assert not self.napp.detect_mismatched_link(mock_link_1)

    @patch('napps.kytos.topology.main.Main.detect_mismatched_link')
    def test_link_status_mismatched(self, mock_detect_mismatched_link):
        """Test link_status_mismatched"""
        mock_link_1 = MagicMock()
        mock_detect_mismatched_link.return_value = True
        assert (self.napp.link_status_mismatched(mock_link_1)
                == EntityStatus.DOWN)

        mock_detect_mismatched_link.return_value = False
        assert self.napp.link_status_mismatched(mock_link_1) is None

    def test_notify_interface_status(self):
        """Test notify_interface_status"""
        mock_buffers_put = MagicMock()
        self.napp.controller.buffers.app.put = mock_buffers_put
        intf_mock = Mock()
        expected_name = "kytos/topology.interface.disabled"
        self.napp.notify_interface_status(intf_mock, 'disabled', 'test')
        assert mock_buffers_put.call_count == 1
        assert mock_buffers_put.call_args_list[0][0][0].name == expected_name

        expected_name = "kytos/topology.interface.up"
        self.napp.notify_interface_status(intf_mock, 'up', 'test')
        assert mock_buffers_put.call_count == 2
        assert mock_buffers_put.call_args_list[1][0][0].name == expected_name
