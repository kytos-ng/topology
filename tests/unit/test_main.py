"""Module to test the main napp file."""
import json
import time
from unittest import TestCase
from unittest.mock import MagicMock, create_autospec, patch

from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.switch import Switch
from kytos.lib.helpers import (get_interface_mock, get_link_mock,
                               get_switch_mock, get_test_client)
from napps.kytos.topology.exceptions import RestoreError
from tests.unit.helpers import get_controller_mock, get_napp_urls


# pylint: disable=too-many-public-methods
class TestMain(TestCase):
    """Test the Main class."""

    # pylint: disable=too-many-public-methods, protected-access,C0302

    def setUp(self):
        """Execute steps before each tests.

        Set the server_name_url_url from kytos/topology
        """
        self.server_name_url = 'http://localhost:8181/api/kytos/topology'

        patch('kytos.core.helpers.run_on_thread', lambda x: x).start()
        # pylint: disable=import-outside-toplevel
        from napps.kytos.topology.main import Main
        self.addCleanup(patch.stopall)

        self.napp = Main(get_controller_mock())

    def test_get_event_listeners(self):
        """Verify all event listeners registered."""
        expected_events = ['kytos/core.shutdown',
                           'kytos/core.shutdown.kytos/topology',
                           'kytos/maintenance.start_link',
                           'kytos/maintenance.end_link',
                           'kytos/maintenance.start_switch',
                           'kytos/maintenance.end_switch',
                           'kytos/storehouse.loaded',
                           '.*.network_status.updated',
                           '.*.interface.is.nni',
                           '.*.connection.lost',
                           '.*.switch.interface.created',
                           '.*.switch.interface.deleted',
                           '.*.switch.interface.link_down',
                           '.*.switch.interface.link_up',
                           '.*.switch.(new|reconnected)',
                           '.*.switch.port.created',
                           'kytos/topology.*.metadata.*']
        actual_events = self.napp.listeners()
        self.assertCountEqual(expected_events, actual_events)

    def test_verify_api_urls(self):
        """Verify all APIs registered."""
        expected_urls = [
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/interfaces'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/switches'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/links'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/switch/<dpid>/disable'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/switch/<dpid>/enable'),
         ({'key': '[key]', 'interface_id': '[interface_id]'},
          {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata/<key>'),
         ({'interface_id': '[interface_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata'),
         ({'interface_id': '[interface_id]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata'),
         ({'interface_disable_id': '[interface_disable_id]'},
          {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_disable_id>/disable'),
         ({'interface_enable_id': '[interface_enable_id]'},
          {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_enable_id>/enable'),
         ({'dpid': '[dpid]', 'key': '[key]'}, {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/switches/<dpid>/metadata/<key>'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/switches/<dpid>/metadata'),
         ({'dpid': '[dpid]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/switches/<dpid>/metadata'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/switches/<dpid>/disable'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/switches/<dpid>/enable'),
         ({'link_id': '[link_id]', 'key': '[key]'}, {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/links/<link_id>/metadata/<key>'),
         ({'link_id': '[link_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/links/<link_id>/metadata'),
         ({'link_id': '[link_id]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/links/<link_id>/metadata'),
         ({'link_id': '[link_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/links/<link_id>/disable'),
         ({'link_id': '[link_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/links/<link_id>/enable')]

        urls = get_napp_urls(self.napp)
        self.assertEqual(expected_urls, urls)

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

        link = self.napp._get_link_or_create(mock_interface_a,
                                             mock_interface_b)
        self.assertEqual(link.endpoint_a.id, dpid_a)
        self.assertEqual(link.endpoint_b.id, dpid_b)

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
        self.assertEqual(response, mock_link)

        response = self.napp._get_link_from_interface(mock_interface_c)
        self.assertEqual(response, None)

    def test_get_topology(self):
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
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/'
        response = api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), expected)

    @patch('napps.kytos.topology.main.StoreHouse.get_data')
    def test_load_network_status(self, mock_storehouse_get_data):
        """Test _load_network_status."""
        link_id = \
            'cf0f4071be426b3f745027f5d22bc61f8312ae86293c9b28e7e66015607a9260'
        dpid_a = '00:00:00:00:00:00:00:01'
        dpid_b = '00:00:00:00:00:00:00:02'
        status = {
            'network_status': {
                'id': 'network_status',
                'links': {
                    link_id: {
                        'enabled': True,
                        'endpoint_a': {
                            'switch': dpid_a,
                            'port_number': 2
                        },
                        'endpoint_b': {
                            'switch': dpid_b,
                            'port_number': 2
                        }
                    }
                },
                'switches': {
                    dpid_a: {
                        'dpid': dpid_a,
                        'enabled': True,
                        'id': dpid_a,
                        'interfaces': {
                            f'{dpid_a}:2': {
                                'enabled': True,
                                'lldp': True,
                                'port_number': 2,
                                'name': 's1-eth2'
                            }
                        }
                    },
                    dpid_b: {
                        'dpid': dpid_b,
                        'enabled': True,
                        'id': dpid_b,
                        'interfaces': {
                            f'{dpid_b}:2': {
                                'enabled': True,
                                'lldp': True,
                                'port_number': 2,
                                'name': 's2-eth2'
                            }
                        }
                    }
                }
            }
        }
        switches_expected = [dpid_a, dpid_b]
        interfaces_expected = [f'{dpid_a}:2', f'{dpid_b}:2']
        links_expected = [link_id]
        mock_storehouse_get_data.return_value = status
        self.napp._load_network_status()
        self.assertListEqual(switches_expected,
                             list(self.napp.controller.switches.keys()))
        interfaces = []
        for switch in self.napp.controller.switches.values():
            for iface in switch.interfaces.values():
                interfaces.append(iface.id)
        self.assertListEqual(interfaces_expected, interfaces)
        self.assertListEqual(links_expected, list(self.napp.links.keys()))

    @patch('napps.kytos.topology.main.StoreHouse.get_data')
    @patch('napps.kytos.topology.main.log')
    def test_load_network_status_fail(self, *args):
        """Test _load_network_status failure."""
        (mock_log, mock_storehouse_get_data) = args
        mock_log.error.return_value = True
        mock_storehouse_get_data.side_effect = FileNotFoundError('xpto')
        self.napp._load_network_status()
        error = 'Fail to load network status from storehouse: xpto'
        mock_log.error.assert_called_with(error)

    @patch('napps.kytos.topology.main.StoreHouse.get_data')
    @patch('napps.kytos.topology.main.log')
    def test_load_network_status_does_nothing(self, *args):
        """Test _load_network_status doing nothing."""
        (mock_log, mock_storehouse_get_data) = args
        mock_log.info.return_value = True
        mock_storehouse_get_data.return_value = {}
        self.napp._load_network_status()
        error = 'There is no status saved to restore.'
        mock_log.info.assert_called_with(error)

    @patch('napps.kytos.topology.main.StoreHouse.get_data')
    @patch('napps.kytos.topology.main.Main._load_switch')
    @patch('napps.kytos.topology.main.log')
    def test_load_network_status_fail_switch(self, *args):
        """Test _load_network_status failure in switch."""
        (mock_log, mock_load_switch, mock_get_data) = args
        status = {
            'network_status': {
                'id': 'network_status',
                'links': {},
                'switches': {
                    '1': {}
                }
            }
        }
        mock_log.error.return_value = True
        mock_get_data.return_value = status
        mock_load_switch.side_effect = Exception('xpto')
        self.napp._load_network_status()
        error = 'Error loading switch: xpto'
        mock_log.error.assert_called_with(error)

    @patch('napps.kytos.topology.main.StoreHouse.get_data')
    @patch('napps.kytos.topology.main.Main._load_link')
    @patch('napps.kytos.topology.main.log')
    def test_load_network_status_fail_link(self, *args):
        """Test _load_network_status failure in link."""
        (mock_log, mock_load_link, mock_get_data) = args
        status = {
            'network_status': {
                'id': 'network_status',
                'switches': {},
                'links': {
                    '1': {}
                }
            }
        }
        mock_log.error.return_value = True
        mock_get_data.return_value = status
        mock_load_link.side_effect = Exception('xpto')
        self.napp._load_network_status()
        error = 'Error loading link 1: xpto'
        mock_log.error.assert_called_with(error)

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_load_switch(self, *args):
        """Test _load_switch."""
        (mock_buffers_put, mock_event) = args
        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_x = "00:00:00:00:00:00:00:XX"
        iface_a = f'{dpid_a}:1'
        switch_attrs = {
            'dpid': dpid_a,
            'enabled': True,
            'id': dpid_a,
            'interfaces': {
                iface_a: {
                    'enabled': True,
                    'lldp': True,
                    'id': iface_a,
                    'switch': dpid_a,
                    'name': 's2-eth1',
                    'port_number': 1
                }
            }
        }
        self.napp._load_switch(dpid_a, switch_attrs)

        self.assertEqual(len(self.napp.controller.switches), 1)
        self.assertIn(dpid_a, self.napp.controller.switches)
        self.assertNotIn(dpid_x, self.napp.controller.switches)
        switch = self.napp.controller.switches[dpid_a]

        self.assertEqual(switch.id, dpid_a)
        self.assertEqual(switch.dpid, dpid_a)
        self.assertTrue(switch.is_enabled())
        self.assertFalse(switch.is_active())

        self.assertEqual(len(switch.interfaces), 1)
        self.assertIn(1, switch.interfaces)
        self.assertNotIn(2, switch.interfaces)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

        interface = switch.interfaces[1]
        self.assertEqual(interface.id, iface_a)
        self.assertEqual(interface.switch.id, dpid_a)
        self.assertEqual(interface.port_number, 1)
        self.assertTrue(interface.is_enabled())
        self.assertTrue(interface.lldp)
        self.assertTrue(interface.uni)
        self.assertFalse(interface.nni)

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

        self.napp._load_switch(dpid_b, switch_attrs)

        self.assertEqual(len(self.napp.controller.switches), 1)
        self.assertIn(dpid_b, self.napp.controller.switches)

        switch = self.napp.controller.switches[dpid_b]
        self.assertEqual(switch.id, dpid_b)
        self.assertEqual(switch.dpid, dpid_b)
        self.assertFalse(switch.is_enabled())
        self.assertFalse(switch.is_active())
        self.assertEqual(switch.description['manufacturer'], 'Nicira, Inc.')
        self.assertEqual(switch.description['hardware'], 'Open vSwitch')
        self.assertEqual(switch.description['software'], '2.10.7')
        self.assertEqual(switch.description['serial'], 'XX serial number')
        self.assertEqual(switch.description['data_path'],
                         'XX Human readable desc of dp')

        self.assertEqual(len(switch.interfaces), 1)
        self.assertIn(1, switch.interfaces)
        self.assertNotIn(2, switch.interfaces)

        interface = switch.interfaces[1]
        self.assertEqual(interface.id, iface_b)
        self.assertEqual(interface.switch.id, dpid_b)
        self.assertEqual(interface.port_number, 1)
        self.assertFalse(interface.is_enabled())
        self.assertFalse(interface.lldp)
        self.assertTrue(interface.uni)
        self.assertFalse(interface.nni)

    def test_load_link(self):
        """Test _load_link."""
        dpid_a = "00:00:00:00:00:00:00:01"
        dpid_b = "00:00:00:00:00:00:00:02"
        mock_switch_a = get_switch_mock(dpid_a, 0x04)
        mock_switch_b = get_switch_mock(dpid_b, 0x04)
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_a.id = dpid_a + ':1'
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_interface_b.id = dpid_b + ':1'
        mock_switch_a.interfaces = {1: mock_interface_a}
        mock_switch_b.interfaces = {1: mock_interface_b}
        self.napp.controller.switches[dpid_a] = mock_switch_a
        self.napp.controller.switches[dpid_b] = mock_switch_b
        link_attrs = {
            'enabled': True,
            'endpoint_a': {
                'switch': dpid_a,
                'port_number': 1
            },
            'endpoint_b': {
                'switch': dpid_b,
                'port_number': 1
            }
        }

        self.napp._load_link(link_attrs)

        self.assertEqual(len(self.napp.links), 1)
        link = list(self.napp.links.values())[0]

        self.assertEqual(link.endpoint_a.id, mock_interface_a.id)
        self.assertEqual(link.endpoint_b.id, mock_interface_b.id)
        self.assertTrue(mock_interface_a.nni)
        self.assertTrue(mock_interface_b.nni)
        self.assertEqual(mock_interface_a.update_link.call_count, 1)
        self.assertEqual(mock_interface_b.update_link.call_count, 1)

        # test enable/disable
        link_id = '4d42dc08522'
        mock_interface_a = get_interface_mock('s1-eth1', 1, mock_switch_a)
        mock_interface_b = get_interface_mock('s2-eth1', 1, mock_switch_b)
        mock_link = get_link_mock(mock_interface_a, mock_interface_b)
        mock_link.id = link_id
        with patch('napps.kytos.topology.main.Main._get_link_or_create',
                   return_value=mock_link):
            # enable link
            link_attrs['enabled'] = True
            self.napp.links = {link_id: mock_link}
            self.napp._load_link(link_attrs)
            self.assertEqual(mock_link.enable.call_count, 1)
            # disable link
            link_attrs['enabled'] = False
            self.napp.links = {link_id: mock_link}
            self.napp._load_link(link_attrs)
            self.assertEqual(mock_link.disable.call_count, 1)

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
            'endpoint_a': {
                'switch': dpid_a,
                'port_number': 999
            },
            'endpoint_b': {
                'switch': dpid_b,
                'port_number': 999
            }
        }
        with self.assertRaises(RestoreError):
            self.napp._load_link(link_attrs_fail)

        link_attrs_fail = {
            'enabled': True,
            'endpoint_a': {
                'switch': '00:00:00:00:00:00:00:99',
                'port_number': 1
            },
            'endpoint_b': {
                'switch': '00:00:00:00:00:00:00:77',
                'port_number': 1
            }
        }
        with self.assertRaises(RestoreError):
            self.napp._load_link(link_attrs_fail)

    @patch('napps.kytos.topology.main.Main.save_status_on_storehouse')
    def test_enable_switch(self, mock_save_status):
        """Test enable_switch."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/switches/{dpid}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(mock_switch.enable.call_count, 1)
        mock_save_status.assert_called()

        # fail case
        mock_switch.enable.call_count = 0
        dpid = "00:00:00:00:00:00:00:02"
        url = f'{self.server_name_url}/v3/switches/{dpid}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(mock_switch.enable.call_count, 0)

    @patch('napps.kytos.topology.main.Main.save_status_on_storehouse')
    def test_disable_switch(self, mock_save_status):
        """Test disable_switch."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/switches/{dpid}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(mock_switch.disable.call_count, 1)
        mock_save_status.assert_called()

        # fail case
        mock_switch.disable.call_count = 0
        dpid = "00:00:00:00:00:00:00:02"
        url = f'{self.server_name_url}/v3/switches/{dpid}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(mock_switch.disable.call_count, 0)

    def test_get_switch_metadata(self):
        """Test get_switch_metadata."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        mock_switch.metadata = "A"
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 200, response.data)

        # fail case
        dpid = "00:00:00:00:00:00:00:02"
        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    def test_add_switch_metadata(self, mock_metadata_changes):
        """Test add_switch_metadata."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)
        payload = {"data": "A"}

        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata'
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 201, response.data)
        mock_metadata_changes.assert_called()

        # fail case
        dpid = "00:00:00:00:00:00:00:02"
        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata'
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 404, response.data)

    def test_add_switch_metadata_wrong_format(self):
        """Test add_switch_metadata_wrong_format."""
        dpid = "00:00:00:00:00:00:00:01"
        api = get_test_client(self.napp.controller, self.napp)
        payload = 'A'

        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata'
        response = api.post(url, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400, response.data)

        payload = None
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 415, response.data)

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    def test_delete_switch_metadata(self, mock_metadata_changes):
        """Test delete_switch_metadata."""
        dpid = "00:00:00:00:00:00:00:01"
        mock_switch = get_switch_mock(dpid)
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        key = "A"
        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata/{key}'
        response = api.delete(url)
        mock_metadata_changes.assert_called()
        self.assertEqual(response.status_code, 200, response.data)

        # fail case
        key = "A"
        dpid = "00:00:00:00:00:00:00:02"
        url = f'{self.server_name_url}/v3/switches/{dpid}/metadata/{key}'
        response = api.delete(url)
        mock_metadata_changes.assert_called()
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.save_status_on_storehouse')
    def test_enable_interfaces(self, mock_save_status):
        """Test enable_interfaces."""
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface_1 = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_2 = get_interface_mock('s1-eth2', 2, mock_switch)
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        interface_id = '00:00:00:00:00:00:00:01:1'
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(mock_interface_1.enable.call_count, 1)
        self.assertEqual(mock_interface_2.enable.call_count, 0)
        mock_save_status.assert_called()

        mock_interface_1.enable.call_count = 0
        mock_interface_2.enable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(mock_interface_1.enable.call_count, 1)
        self.assertEqual(mock_interface_2.enable.call_count, 1)

        # test interface not found
        interface_id = '00:00:00:00:00:00:00:01:3'
        mock_interface_1.enable.call_count = 0
        mock_interface_2.enable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(mock_interface_1.enable.call_count, 0)
        self.assertEqual(mock_interface_2.enable.call_count, 0)

        # test switch not found
        dpid = '00:00:00:00:00:00:00:02'
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(mock_interface_1.enable.call_count, 0)
        self.assertEqual(mock_interface_2.enable.call_count, 0)

    @patch('napps.kytos.topology.main.Main.save_status_on_storehouse')
    def test_disable_interfaces(self, mock_save_status):
        """Test disable_interfaces."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface_1 = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface_2 = get_interface_mock('s1-eth2', 2, mock_switch)
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(mock_interface_1.disable.call_count, 1)
        self.assertEqual(mock_interface_2.disable.call_count, 0)
        mock_save_status.assert_called()

        mock_interface_1.disable.call_count = 0
        mock_interface_2.disable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(mock_interface_1.disable.call_count, 1)
        self.assertEqual(mock_interface_2.disable.call_count, 1)

        # test interface not found
        interface_id = '00:00:00:00:00:00:00:01:3'
        mock_interface_1.disable.call_count = 0
        mock_interface_2.disable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(mock_interface_1.disable.call_count, 0)
        self.assertEqual(mock_interface_2.disable.call_count, 0)

        # test switch not found
        dpid = '00:00:00:00:00:00:00:02'
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(mock_interface_1.disable.call_count, 0)
        self.assertEqual(mock_interface_2.disable.call_count, 0)

    def test_get_interface_metadata(self):
        """Test get_interface_metada."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.metadata = {"metada": "A"}
        mock_switch.interfaces = {1: mock_interface}
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 200, response.data)

        # fail case switch not found
        interface_id = '00:00:00:00:00:00:00:02:1'
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 404, response.data)

        # fail case interface not found
        interface_id = '00:00:00:00:00:00:00:01:2'
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    def test_add_interface_metadata(self, mock_metadata_changes):
        """Test add_interface_metadata."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.metadata = {"metada": "A"}
        mock_switch.interfaces = {1: mock_interface}
        self.napp.controller.switches = {dpid: mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/metadata'
        payload = {"metada": "A"}
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 201, response.data)
        mock_metadata_changes.assert_called()

        # fail case switch not found
        interface_id = '00:00:00:00:00:00:00:02:1'
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/metadata'
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 404, response.data)

        # fail case interface not found
        interface_id = '00:00:00:00:00:00:00:01:2'
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/metadata'
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 404, response.data)

    def test_add_interface_metadata_wrong_format(self):
        """Test add_interface_metadata_wrong_format."""
        dpid = "00:00:00:00:00:00:00:01:1"
        api = get_test_client(self.napp.controller, self.napp)
        payload = 'A'

        url = f'{self.server_name_url}/v3/interfaces/{dpid}/metadata'
        response = api.post(url, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400, response.data)

        payload = None
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 415, response.data)

    def test_delete_interface_metadata(self):
        """Test delete_interface_metadata."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        iface_url = '/v3/interfaces/'
        mock_switch = get_switch_mock(dpid)
        mock_interface = get_interface_mock('s1-eth1', 1, mock_switch)
        mock_interface.remove_metadata.side_effect = [True, False]
        mock_interface.metadata = {"metada": "A"}
        mock_switch.interfaces = {1: mock_interface}
        self.napp.controller.switches = {'00:00:00:00:00:00:00:01':
                                         mock_switch}
        api = get_test_client(self.napp.controller, self.napp)

        key = 'A'
        url = f'{self.server_name_url}{iface_url}{interface_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 200, response.data)

        # fail case switch not found
        key = 'A'
        interface_id = '00:00:00:00:00:00:00:02:1'
        url = f'{self.server_name_url}{iface_url}{interface_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 404, response.data)

        # fail case interface not found
        key = 'A'
        interface_id = '00:00:00:00:00:00:00:01:2'
        url = f'{self.server_name_url}{iface_url}{interface_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 404, response.data)

        # fail case metadata not found
        key = 'A'
        interface_id = '00:00:00:00:00:00:00:01:1'
        url = f'{self.server_name_url}{iface_url}{interface_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.save_status_on_storehouse')
    def test_enable_link(self, mock_save_status):
        """Test enable_link."""
        mock_link = MagicMock(Link)
        self.napp.links = {'1': mock_link}
        api = get_test_client(self.napp.controller, self.napp)
        mock_save_status.return_value = True

        link_id = 1
        url = f'{self.server_name_url}/v3/links/{link_id}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(mock_link.enable.call_count, 1)

        # fail case
        link_id = 2
        url = f'{self.server_name_url}/v3/links/{link_id}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.save_status_on_storehouse')
    def test_disable_link(self, mock_save_status):
        """Test disable_link."""
        mock_link = MagicMock(Link)
        self.napp.links = {'1': mock_link}
        api = get_test_client(self.napp.controller, self.napp)
        mock_save_status.return_value = True

        link_id = 1
        url = f'{self.server_name_url}/v3/links/{link_id}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(mock_link.disable.call_count, 1)

        # fail case
        link_id = 2
        url = f'{self.server_name_url}/v3/links/{link_id}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)

    def test_get_link_metadata(self):
        """Test get_link_metadata."""
        mock_link = MagicMock(Link)
        mock_link.metadata = "A"
        self.napp.links = {'1': mock_link}
        msg_success = {"metadata": "A"}
        api = get_test_client(self.napp.controller, self.napp)

        link_id = 1
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(msg_success, json.loads(response.data))

        # fail case
        link_id = 2
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata'
        response = api.get(url)
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    def test_add_link_metadata(self, mock_metadata_changes):
        """Test add_link_metadata."""
        mock_link = MagicMock(Link)
        mock_link.metadata = "A"
        self.napp.links = {'1': mock_link}
        payload = {"metadata": "A"}
        api = get_test_client(self.napp.controller, self.napp)

        link_id = 1
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata'
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 201, response.data)
        mock_metadata_changes.assert_called()

        # fail case
        link_id = 2
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata'
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 404, response.data)

    def test_add_link_metadata_wrong_format(self):
        """Test add_link_metadata_wrong_format."""
        link_id = 'cf0f4071be426b3f745027f5d22'
        api = get_test_client(self.napp.controller, self.napp)
        payload = "A"

        url = f'{self.server_name_url}/v3/links/{link_id}/metadata'
        response = api.post(url, data=payload,
                            content_type='application/json')
        self.assertEqual(response.status_code, 400, response.data)

        payload = None
        response = api.post(url, data=json.dumps(payload),
                            content_type='application/json')
        self.assertEqual(response.status_code, 415, response.data)

    @patch('napps.kytos.topology.main.Main.notify_metadata_changes')
    def test_delete_link_metadata(self, mock_metadata_changes):
        """Test delete_link_metadata."""
        mock_link = MagicMock(Link)
        mock_link.metadata = "A"
        mock_link.remove_metadata.side_effect = [True, False]
        self.napp.links = {'1': mock_link}
        api = get_test_client(self.napp.controller, self.napp)

        link_id = 1
        key = 'A'
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 200, response.data)
        mock_metadata_changes.assert_called()

        # fail case link not found
        link_id = 2
        key = 'A'
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 404, response.data)

        # fail case metadata not found
        link_id = 1
        key = 'A'
        url = f'{self.server_name_url}/v3/links/{link_id}/metadata/{key}'
        response = api.delete(url)
        self.assertEqual(response.status_code, 404, response.data)

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.update_instance_metadata')
    def test_handle_new_switch(self, *args):
        """Test handle_new_switch."""
        (mock_instance_metadata, mock_notify_topology_update) = args
        mock_event = MagicMock()
        mock_switch = create_autospec(Switch)
        mock_event.content['switch'] = mock_switch
        self.napp.handle_new_switch(mock_event)
        mock_notify_topology_update.assert_called()
        mock_instance_metadata.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_connection_lost(self, mock_notify_topology_update):
        """Test handle connection_lost."""
        mock_event = MagicMock()
        mock_switch = create_autospec(Switch)
        mock_switch.return_value = True
        mock_event.content['source'] = mock_switch
        self.napp.handle_connection_lost(mock_event)
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.update_instance_metadata')
    def test_handle_interface_up(self, *args):
        """Test handle_interface_up."""
        (mock_instance_metadata, mock_notify_topology_update) = args
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_up(mock_event)
        mock_notify_topology_update.assert_called()
        mock_instance_metadata.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_up')
    def test_handle_interface_created(self, mock_handle_interface_up):
        """Test handle interface created."""
        mock_event = MagicMock()
        self.napp.handle_interface_created(mock_event)
        mock_handle_interface_up.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.handle_interface_link_down')
    def test_handle_interface_down(self, *args):
        """Test handle interface down."""
        (mock_handle_interface_link_down, mock_notify_topology_update) = args
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_down(mock_event)
        mock_handle_interface_link_down.assert_called()
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_down')
    def test_interface_deleted(self, mock_handle_interface_link_down):
        """Test interface deleted."""
        mock_event = MagicMock()
        self.napp.handle_interface_deleted(mock_event)
        mock_handle_interface_link_down.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.update_instance_metadata')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_up(self, *args):
        """Test interface link_up."""
        (mock_status_change, mock_instance_metadata, mock_topology_update,
         mock_link_from_interface) = args

        now = time.time()
        mock_event = MagicMock()
        mock_interface_a = create_autospec(Interface)
        mock_interface_a.is_active.return_value = False
        mock_interface_b = create_autospec(Interface)
        mock_interface_b.is_active.return_value = True
        mock_link = create_autospec(Link)
        mock_link.get_metadata.return_value = now
        mock_link.is_active.side_effect = [False, True]
        mock_link.endpoint_a = mock_interface_a
        mock_link.endpoint_b = mock_interface_b
        mock_link_from_interface.return_value = mock_link
        content = {'interface': mock_interface_a}
        mock_event.content = content
        self.napp.link_up_timer = 1
        self.napp.handle_interface_link_up(mock_event)
        mock_topology_update.assert_called()
        mock_instance_metadata.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_down(self, *args):
        """Test interface link down."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface) = args

        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = True
        mock_link_from_interface.return_value = mock_link
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_link_down(mock_event)
        mock_topology_update.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_or_create')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_add_links(self, *args):
        """Test add_links."""
        (mock_notify_topology_update, mock_get_link_or_create) = args
        mock_event = MagicMock()
        self.napp.add_links(mock_event)
        mock_get_link_or_create.assert_called()
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main._get_switches_dict')
    @patch('napps.kytos.topology.main.StoreHouse.save_status')
    def test_save_status_on_store(self, *args):
        """Test save_status_on_storehouse."""
        (mock_save_status, mock_get_switches_dict) = args
        self.napp.save_status_on_storehouse()
        mock_get_switches_dict.assert_called()
        mock_save_status.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_switch_enabled(self, *args):
        """Test notify switch enabled."""
        dpid = "00:00:00:00:00:00:00:01"
        (mock_buffers_put, mock_event) = args
        self.napp.notify_switch_enabled(dpid)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_switch_disabled(self, *args):
        """Test notify switch disabled."""
        dpid = "00:00:00:00:00:00:00:01"
        (mock_buffers_put, mock_event) = args
        self.napp.notify_switch_disabled(dpid)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_topology_update(self, *args):
        """Test notify_topology_update."""
        (mock_buffers_put, mock_event) = args
        self.napp.notify_topology_update()
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_link_status_change(self, *args):
        """Test notify link status change."""
        (mock_buffers_put, mock_event) = args
        mock_link = create_autospec(Link)
        self.napp.notify_link_status_change(mock_link)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    @patch('napps.kytos.topology.main.isinstance')
    def test_notify_metadata_changes(self, *args):
        """Test notify metadata changes."""
        (mock_isinstance, mock_buffers_put, mock_event) = args
        mock_isinstance.return_value = True
        mock_obj = MagicMock()
        mock_action = create_autospec(Switch)
        self.napp.notify_metadata_changes(mock_obj, mock_action)
        mock_event.assert_called()
        mock_isinstance.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_port_created(self, *args):
        """Test notify port created."""
        (mock_buffers_put, mock_kytos_event) = args
        mock_event = MagicMock()
        self.napp.notify_port_created(mock_event)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_save_metadata_on_store(self, *args):
        """Test test_save_metadata_on_store."""
        (mock_buffers_put, mock_kytos_event) = args
        mock_event = MagicMock()
        mock_switch = MagicMock()
        mock_interface = MagicMock()
        mock_link = MagicMock()
        self.napp.store_items = {'switches': mock_switch,
                                 'interfaces': mock_interface,
                                 'links': mock_link}
        # test switches
        mock_event.content = {'switch': mock_switch}
        self.napp.save_metadata_on_store(mock_event)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

        # test interfaces
        mock_event.content = {'interface': mock_interface}
        self.napp.save_metadata_on_store(mock_event)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

        # test link
        mock_event.content = {'link': mock_link}
        self.napp.save_metadata_on_store(mock_event)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_verify_storehouse(self, *args):
        """Test verify_storehouse."""
        (mock_buffers_put, mock_kytos_event) = args
        mock_entities = MagicMock()
        self.napp.verify_storehouse(mock_entities)
        mock_buffers_put.assert_called()
        mock_kytos_event.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_request_retrieve_entities(self, *args):
        """Test retrive_entities."""
        (mock_buffers_put, mock_kytos_event) = args
        mock_event = MagicMock()
        mock_data = MagicMock()
        mock_error = MagicMock()
        mock_event.content = {"namespace": "test_box"}
        self.napp.request_retrieve_entities(mock_event, mock_data, mock_error)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

        self.napp.request_retrieve_entities(mock_event, None, mock_error)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_maintenance_start(self, status_change_mock):
        """Test handle_link_maintenance_start."""
        link1 = MagicMock()
        link1.id = 2
        link2 = MagicMock()
        link2.id = 3
        link3 = MagicMock()
        link3.id = 4
        content = {'links': [link1, link2]}
        event = MagicMock()
        event.content = content
        self.napp.links = {2: link1, 4: link3}
        self.napp.handle_link_maintenance_start(event)
        status_change_mock.assert_called_once_with(link1, reason='maintenance')

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_maintenance_end(self, status_change_mock):
        """Test handle_link_maintenance_end."""
        link1 = MagicMock()
        link1.id = 2
        link2 = MagicMock()
        link2.id = 3
        link3 = MagicMock()
        link3.id = 4
        content = {'links': [link1, link2]}
        event = MagicMock()
        event.content = content
        self.napp.links = {2: link1, 4: link3}
        self.napp.handle_link_maintenance_end(event)
        status_change_mock.assert_called_once_with(link1, reason='maintenance')

    @patch('napps.kytos.topology.main.Main.handle_link_down')
    def test_handle_switch_maintenance_start(self, handle_link_down_mock):
        """Test handle_switch_maintenance_start."""
        switch1 = MagicMock()
        interface1 = MagicMock()
        interface1.is_active.return_value = True
        interface2 = MagicMock()
        interface2.is_active.return_value = False
        interface3 = MagicMock()
        interface3.is_active.return_value = True
        switch1.interfaces = {1: interface1, 2: interface2, 3: interface3}
        switch2 = MagicMock()
        interface4 = MagicMock()
        interface4.is_active.return_value = False
        interface5 = MagicMock()
        interface5.is_active.return_value = True
        switch2.interfaces = {1: interface4, 2: interface5}
        content = {'switches': [switch1, switch2]}
        event = MagicMock()
        event.content = content
        self.napp.handle_switch_maintenance_start(event)
        self.assertEqual(handle_link_down_mock.call_count, 3)

    @patch('napps.kytos.topology.main.Main.handle_link_up')
    def test_handle_switch_maintenance_end(self, handle_link_up_mock):
        """Test handle_switch_maintenance_end."""
        switch1 = MagicMock()
        interface1 = MagicMock()
        interface1.is_active.return_value = True
        interface2 = MagicMock()
        interface2.is_active.return_value = False
        interface3 = MagicMock()
        interface3.is_active.return_value = True
        switch1.interfaces = {1: interface1, 2: interface2, 3: interface3}
        switch2 = MagicMock()
        interface4 = MagicMock()
        interface4.is_active.return_value = False
        interface5 = MagicMock()
        interface5.is_active.return_value = True
        switch2.interfaces = {1: interface4, 2: interface5}
        content = {'switches': [switch1, switch2]}
        event = MagicMock()
        event.content = content
        self.napp.handle_switch_maintenance_end(event)
        self.assertEqual(handle_link_up_mock.call_count, 5)
