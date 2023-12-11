"""Module to test the main napp file."""
# pylint: disable=import-error,no-name-in-module,wrong-import-order
# pylint: disable=import-outside-toplevel,attribute-defined-outside-init
import pytest
import time
from datetime import timedelta
from unittest.mock import MagicMock, create_autospec, patch, call

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
    Main.get_topo_controller = MagicMock()
    napp = Main(get_controller_mock())
    napp.notify_topology_update = MagicMock()
    napp.notify_link_status_change = MagicMock()

    link = MagicMock(id="some_id", status=status)
    napp.handle_link_liveness_status(link, liveness_status)

    add_link_meta = napp.topo_controller.add_link_metadata
    add_link_meta.assert_called_with(link.id, {"liveness_status":
                                               liveness_status})
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
            'kytos/.*.liveness.(up|down)',
            'kytos/.*.liveness.disabled',
            '.*.switch.port.created',
            'kytos/topology.notify_link_up_if_status',
            'topology.interruption.start',
            'topology.interruption.end',
            'kytos/core.interface_tags',
        ]
        actual_events = self.napp.listeners()
        assert sorted(expected_events) == sorted(actual_events)

    def test_get_link_or_create(self):
        """Test _get_link_or_create."""
        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_b = "00:00:00:00:00:00:00:02"
        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_switch_b = get_switch_mock(dpid_b, 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_interface_a.id = dpid_a
        mock_interface_b.id = dpid_b

        link, created = self.napp._get_link_or_create(mock_interface_a,
                                                      mock_interface_b)
        assert created
        assert link.endpoint_a.id == dpid_a
        assert link.endpoint_b.id == dpid_b

        link, created = self.napp._get_link_or_create(mock_interface_a,
                                                      mock_interface_b)
        assert not created

    def test_get_link_from_interface(self):
        """Test _get_link_from_interface."""
        mock_switch_a = get_switch_mock("00:00:00:00:00:00:00:01", 0x04)
        mock_switch_b = get_switch_mock("00:00:00:00:00:00:00:02", 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_interface_c = get_interface_mock('s2-eth1', 2, mock_switch_b)
        mock_link = get_link_mock(mock_interface_a, mock_interface_b)
        self.napp.links = {'0e2b5d7bc858b9f38db11b69': mock_link}
        response = self.napp._get_link_from_interface(mock_interface_a)
        assert response == mock_link

        response = self.napp._get_link_from_interface(mock_interface_c)
        assert not response

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

        self.napp.links = {"cf0f4071be4": mock_link}
        mock_link.as_dict.return_value = {"id": "cf0f4071be4"}
        endpoint = f"{self.base_endpoint}/"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == expected

    def test_load_topology(self):
        """Test load_topology."""
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
        assert links_expected == list(self.napp.links.keys())

    @patch('napps.kytos.topology.main.Main._load_switch')
    @patch('napps.kytos.topology.main.Main._load_link')
    def test_load_topology_does_nothing(self, *args):
        """Test _load_network_status doing nothing."""
        (mock_load_link, mock_load_switch) = args
        self.napp.topo_controller.get_topology.return_value = {
            "topology": {"switches": {}, "links": {}}
        }
        self.napp.topo_controller.load_topology()
        assert mock_load_link.call_count == 0
        assert mock_load_switch.call_count == 0

    @patch('napps.kytos.topology.main.Main._load_switch')
    @patch('napps.kytos.topology.main.log')
    def test_load_topology_fail_switch(self, *args):
        """Test load_topology failure in switch."""
        (mock_log, mock_load_switch) = args
        topology = {
            'topology': {
                'links': {},
                'switches': {
                    '1': {}
                }
            }
        }
        mock_log.error.return_value = True
        self.napp.topo_controller.get_topology.return_value = topology
        mock_load_switch.side_effect = Exception('xpto')
        self.napp.load_topology()
        error = 'Error loading switch: xpto'
        mock_log.error.assert_called_with(error)

    @patch('napps.kytos.topology.main.Main._load_link')
    @patch('napps.kytos.topology.main.log')
    def test_load_topology_fail_link(self, *args):
        """Test load_topology failure in link."""
        (mock_log, mock_load_link) = args
        topology = {
            'topology': {
                'switches': {},
                'links': {
                    '1': {}
                }
            }
        }
        mock_log.error.return_value = True
        self.napp.topo_controller.get_topology.return_value = topology
        mock_load_link.side_effect = Exception('xpto')
        self.napp.load_topology()
        error = 'Error loading link 1: xpto'
        mock_log.error.assert_called_with(error)

    @patch('napps.kytos.topology.main.Main.load_interfaces_tags_values')
    @patch('napps.kytos.topology.main.KytosEvent')
    def test_load_switch(self, *args):
        """Test _load_switch."""
        (mock_event, mock_load_tags) = args
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
        self.napp._load_switch(dpid_a, switch_attrs)

        assert len(self.napp.controller.switches) == 1
        assert dpid_a in self.napp.controller.switches
        assert dpid_x not in self.napp.controller.switches
        switch = self.napp.controller.switches[dpid_a]
        interface_details = self.napp.topo_controller.get_interfaces_details
        interface_details.assert_called_once_with([iface_a])
        mock_load_tags.assert_called()

        assert switch.id == dpid_a
        assert switch.dpid == dpid_a
        assert switch.is_enabled()
        assert not switch.is_active()

        assert len(switch.interfaces) == 1
        assert 1 in switch.interfaces
        assert 2 not in switch.interfaces
        mock_event.assert_called()
        mock_buffers_put.assert_called()

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
        self.napp._load_switch(dpid_b, switch_attrs)
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
        interface_details = [{
            "id": mock_interface_a.id,
            "available_tags": ava_tags,
            "tag_ranges": tag_ranges,
            "special_available_tags": special_available_tags,
            "special_tags": special_tags
        }]
        self.napp.load_interfaces_tags_values(mock_switch_a,
                                              interface_details)
        set_method = mock_interface_a.set_available_tags_tag_ranges
        set_method.assert_called_once_with(
            ava_tags, tag_ranges,
            special_available_tags, special_tags
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
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_interface_b.id = dpid_b + ':1'
        mock_interface_b.available_tags = [1, 2, 3]
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

        self.napp._load_link(link_attrs)

        assert len(self.napp.links) == 1
        link = list(self.napp.links.values())[0]

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
        with patch('napps.kytos.topology.main.Main._get_link_or_create',
                   return_value=(mock_link, True)):
            # enable link
            link_attrs['enabled'] = True
            self.napp.links = {link_id: mock_link}
            self.napp._load_link(link_attrs)
            assert mock_link.enable.call_count == 1
            # disable link
            link_attrs['enabled'] = False
            self.napp.links = {link_id: mock_link}
            self.napp._load_link(link_attrs)
            assert mock_link.disable.call_count == 1

    @patch('napps.kytos.topology.main.Main._get_link_or_create')
    def test_fail_load_link(self, get_link_or_create_mock):
        """Test fail load_link."""
        dpid_a = '00:00:00:00:00:00:00:01'
        dpid_b = '00:00:00:00:00:00:00:02'
        link_id = '4d42dc08522'
        mock_switch_a = get_switch_mock(dpid_a)
        mock_switch_b = get_switch_mock(dpid_b)
        mock_interface_a_1 = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b_1 = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_link = get_link_mock(mock_interface_a_1, mock_interface_b_1)
        mock_link.id = link_id
        self.napp.links = {link_id: mock_link}
        get_link_or_create_mock.return_value = mock_link

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
            self.napp._load_link(link_attrs_fail)

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
            self.napp._load_link(link_attrs_fail)

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

    @patch('napps.kytos.topology.main.Main.notify_switch_links_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_disable_switch(self, mock_notify_topo, mock_sw_l_status):
        """Test disable_switch."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}

        endpoint = f"{self.base_endpoint}/switches/{dpid}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_switch.disable.call_count == 1
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
        self, mock_metadata_changes, event_loop
    ):
        """Test add_switch_metadata."""
        self.napp.controller.loop = event_loop
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

    async def test_add_switch_metadata_wrong_format(self, event_loop):
        """Test add_switch_metadata_wrong_format."""
        self.napp.controller.loop = event_loop
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
        self, mock_metadata_changes, event_loop
    ):
        """Test delete_switch_metadata."""
        self.napp.controller.loop = event_loop
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

        # fail case
        key = "A"
        dpid = "00:00:00:00:00:00:00:02"
        endpoint = f"{self.base_endpoint}/switches/{dpid}/metadata/{key}"
        response = await self.api_client.delete(endpoint)
        assert mock_metadata_changes.call_count == 1
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_enable_interfaces(self, mock_notify_topo):
        """Test enable_interfaces."""
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface_1 = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_2 = get_interface_mock('s1-eth2', 2, mock_switch)
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}
        self.napp.controller.switches = {dpid: mock_switch}

        interface_id = '00:00:00:00:00:00:00:01:1'

        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 200
        assert mock_interface_1.enable.call_count == 1
        assert mock_interface_2.enable.call_count == 0
        self.napp.topo_controller.enable_interface.assert_called_with(
            interface_id
        )
        mock_notify_topo.assert_called()

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

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_disable_interfaces(self, mock_notify_topo):
        """Test disable_interfaces."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface_1 = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_2 = get_interface_mock('s1-eth2', 2, mock_switch)
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
        assert mock_interface_2.disable.call_count == 1

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
        self, mock_metadata_changes, event_loop
    ):
        """Test add_interface_metadata."""
        self.napp.controller.loop = event_loop
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

    async def test_add_interface_metadata_wrong_format(self, event_loop):
        """Test add_interface_metadata_wrong_format."""
        self.napp.controller.loop = event_loop
        interface_id = "00:00:00:00:00:00:00:01:1"
        endpoint = f"{self.base_endpoint}/interfaces/{interface_id}/metadata"
        response = await self.api_client.post(endpoint, json='A')
        assert response.status_code == 400
        response = await self.api_client.post(endpoint, json=None)
        assert response.status_code == 415

    async def test_delete_interface_metadata(self, event_loop):
        """Test delete_interface_metadata."""
        self.napp.controller.loop = event_loop
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

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_enable_link(self, mock_notify_topo):
        """Test enable_link."""
        mock_link = MagicMock(Link)
        self.napp.links = {'1': mock_link}

        link_id = "1"
        endpoint = f"{self.base_endpoint}/links/{link_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_link.enable.call_count == 1
        self.napp.topo_controller.enable_link.assert_called_with(link_id)
        mock_notify_topo.assert_called()

        # fail case
        link_id = "2"
        endpoint = f"{self.base_endpoint}/links/{link_id}/enable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 404

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    async def test_disable_link(self, mock_notify_topo):
        """Test disable_link."""
        mock_link = MagicMock(Link)
        self.napp.links = {'1': mock_link}

        link_id = "1"
        endpoint = f"{self.base_endpoint}/links/{link_id}/disable"
        response = await self.api_client.post(endpoint)
        assert response.status_code == 201
        assert mock_link.disable.call_count == 1
        assert mock_notify_topo.call_count == 1
        self.napp.topo_controller.disable_link.assert_called_with(link_id)

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
        mock_link.metadata = "A"
        self.napp.links = {'1': mock_link}
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
        mock_topology_update,
        event_loop
    ):
        """Test add_link_metadata."""
        self.napp.controller.loop = event_loop
        mock_link = MagicMock(Link)
        mock_link.metadata = "A"
        self.napp.links = {'1': mock_link}
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

    async def test_add_link_metadata_wrong_format(self, event_loop):
        """Test add_link_metadata_wrong_format."""
        self.napp.controller.loop = event_loop
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
        mock_link.metadata = {"A": "A"}
        mock_link.remove_metadata.side_effect = [True, False]
        self.napp.links = {'1': mock_link}

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

    @patch('napps.kytos.topology.main.Main.handle_interface_link_up')
    def test_handle_interface_created(self, mock_link_up):
        """Test handle_interface_created."""
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        mock_event.content = {'interface': mock_interface}
        self.napp.handle_interface_created(mock_event)
        mock_link_up.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_link_up')
    def test_handle_interface_created_inactive(self, mock_link_up):
        """Test handle_interface_created inactive."""
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        mock_event.content = {'interface': mock_interface}
        mock_interface.is_active.return_value = False
        self.napp.handle_interface_created(mock_event)
        mock_link_up.assert_not_called()

    def test_handle_interfaces_created(self):
        """Test handle_interfaces_created."""
        buffers_app_mock = MagicMock()
        self.napp.controller.buffers.app = buffers_app_mock
        mock_switch = create_autospec(Switch)
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_interface.id = "1"
        mock_interface.switch = mock_switch
        mock_interface_two = create_autospec(Interface)
        mock_interface_two.id = "2"
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

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_link_up_if_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_interface_link_up(self, *args):
        """Test interface link_up."""
        (mock_notify_topology_update,
         mock_notify_link_up_if_status,
         mock_link_from_interface) = args

        tnow = time.time()
        mock_interface_a = create_autospec(Interface)
        mock_interface_a.is_active.return_value = False
        mock_interface_b = create_autospec(Interface)
        mock_interface_b.is_active.return_value = True
        mock_link = create_autospec(Link)
        mock_link.get_metadata.return_value = tnow
        mock_link.is_active.side_effect = [False, True]
        mock_link.endpoint_a = mock_interface_a
        mock_link.endpoint_b = mock_interface_b
        mock_link_from_interface.return_value = mock_link
        mock_link.status = EntityStatus.UP
        event = KytosEvent("kytos.of_core.switch.interface.down")
        self.napp.handle_interface_link_up(mock_interface_a, event)
        mock_notify_topology_update.assert_called()
        mock_link.extend_metadata.assert_called()
        mock_link.activate.assert_called()
        mock_notify_link_up_if_status.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_down(self, *args):
        """Test interface link down."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface) = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = True
        mock_link_from_interface.return_value = mock_link
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

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_down(self, *args):
        """Test interface link down."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface) = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = True
        mock_link_from_interface.return_value = mock_link
        self.napp.handle_link_down(mock_interface)
        mock_interface.deactivate.assert_not_called()
        mock_link.deactivate.assert_called()
        mock_link.extend_metadata.assert_called()
        assert mock_topology_update.call_count == 1
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_down_not_active(self, *args):
        """Test interface link down with link not active."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface) = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = False
        mock_link_from_interface.return_value = mock_link
        mock_link.get_metadata.return_value = False
        self.napp.handle_link_down(mock_interface)
        mock_topology_update.assert_called()
        mock_status_change.assert_not_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_down_not_active_last_status(self, *args):
        """Test interface link down with link not active."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface) = args

        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = False
        mock_link_from_interface.return_value = mock_link
        mock_link.get_metadata.return_value = True
        self.napp.handle_link_down(mock_interface)
        mock_topology_update.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_link_up_if_status')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_link_up(self, *args):
        """Test handle link up."""
        (mock_notify_topology_update,
         mock_notify_link_up_if_status,
         mock_link_from_interface) = args

        mock_interface = create_autospec(Interface)
        mock_link = MagicMock(status=EntityStatus.UP)
        mock_link.is_active.return_value = True
        mock_link_from_interface.return_value = mock_link
        self.napp.handle_link_up(mock_interface)
        mock_interface.activate.assert_not_called()
        assert mock_notify_link_up_if_status.call_count == 1
        mock_notify_topology_update.assert_called()

    @patch('time.sleep')
    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_up_intf_down(self, *args):
        """Test handle link up but one intf down."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface, _) = args

        mock_interface = create_autospec(Interface)
        mock_link = MagicMock()
        mock_link.endpoint_a.is_active.return_value = False
        mock_link.is_active.return_value = False
        mock_link_from_interface.return_value = mock_link
        self.napp.handle_link_up(mock_interface)
        mock_interface.activate.assert_not_called()
        assert mock_topology_update.call_count == 1
        mock_status_change.assert_not_called()

    @patch('napps.kytos.topology.main.Main._get_link_or_create')
    @patch('napps.kytos.topology.main.Main.notify_link_up_if_status')
    def test_add_links(self, *args):
        """Test add_links."""
        (mock_notify_link_up_if_status,
         mock_get_link_or_create) = args

        mock_link = MagicMock()
        mock_get_link_or_create.return_value = (mock_link, True)
        mock_event = MagicMock()
        mock_intf_a = MagicMock()
        mock_intf_b = MagicMock()
        mock_event.content = {
            "interface_a": mock_intf_a,
            "interface_b": mock_intf_b
        }
        self.napp.add_links(mock_event)
        mock_link.extend_metadata.assert_called()
        mock_get_link_or_create.assert_called()
        mock_notify_link_up_if_status.assert_called()
        mock_intf_a.update_link.assert_called()
        mock_intf_b.update_link.assert_called()
        mock_link.endpoint_a = mock_intf_a
        mock_link.endpoint_b = mock_intf_b

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

    def test_get_links_from_interfaces(self) -> None:
        """Test get_links_from_interfaces."""
        interfaces = [MagicMock(id=f"intf{n}") for n in range(4)]
        links = {
            "link1": MagicMock(id="link1",
                               endpoint_a=interfaces[0],
                               endpoint_b=interfaces[1]),
            "link2": MagicMock(id="link2",
                               endpoint_a=interfaces[2],
                               endpoint_b=interfaces[3]),
        }
        self.napp.links = links
        response = self.napp.get_links_from_interfaces(interfaces)
        assert links == response
        response = self.napp.get_links_from_interfaces(interfaces[:2])
        assert response == {"link1": links["link1"]}

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
        self.napp.links = links
        self.napp.notify_topology_update = MagicMock()
        self.napp.notify_link_status_change = MagicMock()

        self.napp.handle_link_liveness_disabled(interfaces)

        bulk_delete = self.napp.topo_controller.bulk_delete_link_metadata_key
        assert bulk_delete.call_count == 1
        assert self.napp.notify_topology_update.call_count == 1
        assert self.napp.notify_link_status_change.call_count == len(links)

    def test_link_status_hook_link_up_timer(self) -> None:
        """Test status hook link up timer."""
        last_change = time.time() - self.napp.link_up_timer + 5
        link = MagicMock(metadata={"last_status_change": last_change})
        link.is_active.return_value = True
        link.is_enabled.return_value = True
        res = self.napp.link_status_hook_link_up_timer(link)
        assert res == EntityStatus.DOWN

        last_change = time.time() - self.napp.link_up_timer
        link.metadata["last_status_change"] = last_change
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
        link.get_metadata.return_value = now()
        assert not self.napp.notify_link_up_if_status(link, "link up")
        link.update_metadata.assert_not_called()
        mock_notify_topo.assert_not_called()
        mock_notify_link.assert_not_called()

        link = MagicMock(status=EntityStatus.UP)
        link.get_metadata.return_value = now() - timedelta(seconds=60)
        assert not self.napp.notify_link_up_if_status(link, "link up")
        link.update_metadata.assert_called()
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
        link1 = MagicMock()
        link1.endpoint_a.switch = mock_switch
        self.napp.links = {1: link1}

        self.napp.notify_switch_links_status(mock_switch, "link enabled")
        assert self.napp.controller.buffers.app.put.call_count == 1

        self.napp.notify_switch_links_status(mock_switch, "link disabled")
        assert self.napp.controller.buffers.app.put.call_count == 1
        assert mock_notify_link_status_change.call_count == 1

        # Without notification
        link1.endpoint_a.switch = None
        self.napp.notify_switch_links_status(mock_switch, "link enabled")
        assert self.napp.controller.buffers.app.put.call_count == 1

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    def test_notify_interface_link_status(self, *args):
        """Test interface links notification when enable"""
        (mock_get_link_from_interface,
         mock_notify_link_status_change) = args
        buffers_app_mock = MagicMock()
        self.napp.controller.buffers.app = buffers_app_mock
        mock_link = MagicMock()
        mock_get_link_from_interface.return_value = mock_link
        self.napp.notify_interface_link_status(MagicMock(), "link enabled")
        assert mock_get_link_from_interface.call_count == 1
        assert self.napp.controller.buffers.app.put.call_count == 1

        self.napp.notify_interface_link_status(MagicMock(), "link disabled")
        assert mock_get_link_from_interface.call_count == 2
        assert mock_notify_link_status_change.call_count == 1
        assert self.napp.controller.buffers.app.put.call_count == 1

        # Without notification
        mock_get_link_from_interface.return_value = None
        self.napp.notify_interface_link_status(MagicMock(), "link enabled")
        assert mock_get_link_from_interface.call_count == 3
        assert self.napp.controller.buffers.app.put.call_count == 1

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interruption_start(
        self,
        mock_notify_link_status_change,
        mock_notify_topology_update
    ):
        """Tests processing of received interruption start events."""
        link_a = MagicMock()
        link_b = MagicMock()
        link_c = MagicMock()
        self.napp.links = {
            'link_a': link_a,
            'link_b': link_b,
            'link_c': link_c,
        }
        event = KytosEvent(
            "topology.interruption.start",
            {
                'type': 'test_interruption',
                'switches': [
                ],
                'interfaces': [
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

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interruption_end(
        self,
        mock_notify_link_status_change,
        mock_notify_topology_update
    ):
        """Tests processing of received interruption end events."""
        link_a = MagicMock()
        link_b = MagicMock()
        link_c = MagicMock()
        self.napp.links = {
            'link_a': link_a,
            'link_b': link_b,
            'link_c': link_c,
        }
        event = KytosEvent(
            "topology.interruption.start",
            {
                'type': 'test_interruption',
                'switches': [
                ],
                'interfaces': [
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

    async def test_set_tag_range(self, event_loop):
        """Test set_tag_range"""
        self.napp.controller.loop = event_loop
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.set_tag_ranges = MagicMock()
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
        assert args[0] == payload['tag_ranges']
        assert args[1] == payload['tag_type']
        assert self.napp.handle_on_interface_tags.call_count == 1

    async def test_set_tag_range_not_found(self, event_loop):
        """Test set_tag_range. Not found"""
        self.napp.controller.loop = event_loop
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

    async def test_set_tag_range_tag_error(self, event_loop):
        """Test set_tag_range TagRangeError"""
        self.napp.controller.loop = event_loop
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.set_tag_ranges = MagicMock()
        mock_interface.set_tag_ranges.side_effect = KytosSetTagRangeError("")
        mock_interface.notify_interface_tags = MagicMock()
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

    async def test_set_tag_range_type_error(self, event_loop):
        """Test set_tag_range TagRangeError"""
        self.napp.controller.loop = event_loop
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

    async def test_delete_tag_range(self, event_loop):
        """Test delete_tag_range"""
        self.napp.controller.loop = event_loop
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.remove_tag_ranges = MagicMock()
        self.napp.handle_on_interface_tags = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.delete(url)
        assert response.status_code == 200
        assert mock_interface.remove_tag_ranges.call_count == 1

    async def test_delete_tag_range_not_found(self, event_loop):
        """Test delete_tag_range. Not found"""
        self.napp.controller.loop = event_loop
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.remove_tag_ranges = MagicMock()
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = None
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.delete(url)
        assert response.status_code == 404
        assert mock_interface.remove_tag_ranges.call_count == 0

    async def test_delete_tag_range_type_error(self, event_loop):
        """Test delete_tag_range TagRangeError"""
        self.napp.controller.loop = event_loop
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.remove_tag_ranges = MagicMock()
        remove_tag = mock_interface.remove_tag_ranges
        remove_tag.side_effect = KytosTagtypeNotSupported("")
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = mock_interface
        url = f"{self.base_endpoint}/interfaces/{interface_id}/tag_ranges"
        response = await self.api_client.delete(url)
        assert response.status_code == 400

    async def test_get_all_tag_ranges(self, event_loop):
        """Test get_all_tag_ranges"""
        self.napp.controller.loop = event_loop
        dpid = '00:00:00:00:00:00:00:01'
        switch = get_switch_mock(dpid)
        interface = get_interface_mock('s1-eth1', 1, switch)
        tags = {'vlan': [[1, 4095]]}
        special_tags = {'vlan': ["vlan"]}
        interface.tag_ranges = tags
        interface.available_tags = tags
        interface.special_available_tags = special_tags
        interface.special_tags = special_tags
        switch.interfaces = {1: interface}
        self.napp.controller.switches = {dpid: switch}
        url = f"{self.base_endpoint}/interfaces/tag_ranges"
        response = await self.api_client.get(url)
        expected = {dpid + ":1": {
            'available_tags': tags,
            'tag_ranges': tags,
            'special_available_tags': special_tags,
            'special_tags': special_tags
        }}
        assert response.status_code == 200
        assert response.json() == expected

    async def test_get_tag_ranges_by_intf(self, event_loop):
        """Test get_tag_ranges_by_intf"""
        self.napp.controller.loop = event_loop
        dpid = '00:00:00:00:00:00:00:01'
        switch = get_switch_mock(dpid)
        interface = get_interface_mock('s1-eth1', 1, switch)
        tags = {'vlan': [[1, 4095]]}
        special_tags = {'vlan': ["vlan"]}
        interface.tag_ranges = tags
        interface.available_tags = tags
        interface.special_available_tags = special_tags
        interface.special_tags = special_tags
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = interface
        url = f"{self.base_endpoint}/interfaces/{dpid}:1/tag_ranges"
        response = await self.api_client.get(url)
        expected = {
            '00:00:00:00:00:00:00:01:1': {
                "available_tags": tags,
                "tag_ranges": tags,
                'special_available_tags': special_tags,
                'special_tags': special_tags
            }
        }
        assert response.status_code == 200
        assert response.json() == expected

    async def test_get_tag_ranges_by_intf_error(self, event_loop):
        """Test get_tag_ranges_by_intf with NotFound"""
        self.napp.controller.loop = event_loop
        dpid = '00:00:00:00:00:00:00:01'
        self.napp.controller.get_interface_by_id = MagicMock()
        self.napp.controller.get_interface_by_id.return_value = None
        url = f"{self.base_endpoint}/interfaces/{dpid}:1/tag_ranges"
        response = await self.api_client.get(url)
        assert response.status_code == 404

    async def test_set_special_tags(self, event_loop):
        """Test set_special_tags"""
        self.napp.controller.loop = event_loop
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
        self.napp.links = {link_id: mock_link}

        call_count = self.napp.controller.buffers.app.put.call_count
        endpoint = f"{self.base_endpoint}/links/{link_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 200
        assert self.napp.topo_controller.delete_link.call_count == 1
        assert len(self.napp.links) == 0
        call_count += 2
        assert self.napp.controller.buffers.app.put.call_count == call_count

        # Link is up
        self.napp.links = {link_id: mock_link}
        mock_link.status = EntityStatus.UP
        endpoint = f"{self.base_endpoint}/links/{link_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 409
        assert self.napp.topo_controller.delete_link.call_count == 1
        assert self.napp.controller.buffers.app.put.call_count == call_count

        # Link does not exist
        del self.napp.links[link_id]
        endpoint = f"{self.base_endpoint}/links/{link_id}"
        response = await self.api_client.delete(endpoint)
        assert response.status_code == 404
        assert self.napp.topo_controller.delete_link.call_count == 1
        assert self.napp.controller.buffers.app.put.call_count == call_count
