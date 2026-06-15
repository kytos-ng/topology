"""Module to test the main napp file."""
import asyncio

from unittest.mock import MagicMock

from kytos.core.events import KytosEvent
from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.switch import Switch
from kytos.lib.helpers import (get_controller_mock, get_connection_mock,
                               get_test_client)


class TestMain:
    """Test tag manipulation in the Main class."""
    # pylint: disable=too-many-statements

    def setup_method(self):
        """Execute steps before each tests."""
        # pylint: disable=attribute-defined-outside-init
        # patch('kytos.core.helpers.run_on_thread', lambda x: x).start()
        # pylint: disable-next=import-outside-toplevel
        from napps.kytos.topology.main import Main
        Main.get_topo_controller = MagicMock()
        controller = get_controller_mock()
        self.napp = Main(controller)
        self.api_client = get_test_client(controller, self.napp)
        self.base_url = 'kytos/topology/v3'

        self.switch_1 = Switch("00:00:00:00:00:00:00:01")
        connection = get_connection_mock(0x04, self.switch_1)
        connection.port = 'port'
        self.switch_1.update_connection(connection)
        self.interface_1_1 = Interface("s1-eth1", 1, self.switch_1)
        self.interface_1_2 = Interface("s1-eth2", 2, self.switch_1)
        self.interface_1_2.set_available_tags_tag_ranges(
            available_tag={"vlan": []},
            tag_ranges={"vlan": []},
            default_tag_ranges={"vlan": []},
            special_available_tags={"vlan": []},
            special_tags={"vlan": []},
            default_special_tags={"vlan": []},
            supported_tag_types=frozenset({'vlan'})
        )
        self.switch_1.interfaces = {
            self.interface_1_1.port_number: self.interface_1_1,
            self.interface_1_2.port_number: self.interface_1_2,
        }

        self.switch_2 = Switch("00:00:00:00:00:00:00:02")
        connection = get_connection_mock(0x04, self.switch_2)
        connection.port = 'port'
        self.switch_2.update_connection(connection)
        self.interface_2_1 = Interface("s2-eth1", 1, self.switch_2)
        self.interface_2_2 = Interface("s2-eth2", 2, self.switch_2)
        self.interface_2_2.set_available_tags_tag_ranges(
            available_tag={"vlan": []},
            tag_ranges={"vlan": []},
            default_tag_ranges={"vlan": []},
            special_available_tags={"vlan": []},
            special_tags={"vlan": []},
            default_special_tags={"vlan": []},
            supported_tag_types=frozenset({'vlan'})
        )
        self.switch_2.interfaces = {
            self.interface_2_1.port_number: self.interface_2_1,
            self.interface_2_2.port_number: self.interface_2_2,
        }

        self.switch_3 = Switch("00:00:00:00:00:00:00:03")
        connection = get_connection_mock(0x04, self.switch_3)
        connection.port = 'port'
        self.switch_3.update_connection(connection)
        self.interface_3_1 = Interface("s3-eth1", 1, self.switch_3)
        self.switch_3.interfaces = {
            self.interface_3_1.port_number: self.interface_3_1,
        }

        self.napp.controller.switches = {
            self.switch_1.id: self.switch_1,
            self.switch_2.id: self.switch_2,
            self.switch_3.id: self.switch_3,
        }

        self.link_1_2 = Link(self.interface_1_2, self.interface_2_2)
        self.interface_1_2.link = self.link_1_2
        self.interface_2_2.link = self.link_1_2
        self.link_1_2.set_available_tags_tag_ranges(
            available_tag={"vlan": [[1, 4094]]},
            tag_ranges={"vlan": [[1, 4094]]},
            default_tag_ranges={"vlan": [[1, 4094]]},
            special_available_tags={"vlan": ["untagged", "any"]},
            special_tags={"vlan": ["untagged", "any"]},
            default_special_tags={"vlan": ["untagged", "any"]},
            supported_tag_types=frozenset({'vlan'})
        )

        self.napp.controller.links = {
            self.link_1_2.id: self.link_1_2,
        }

        entities = [
            self.switch_1,
            self.interface_1_1,
            self.interface_1_2,
            self.switch_2,
            self.interface_2_1,
            self.interface_2_2,
            self.switch_3,
            self.interface_3_1,
            self.link_1_2,
        ]

        for entity in entities:
            entity.enable()
            entity.activate()

    async def test_get_tags(self):
        """Test get_topology."""
        self.napp.controller.loop = asyncio.get_running_loop()
        expected = {
            "topology": {
                "switches": {
                    self.switch_1.id: self.switch_1.as_dict(),
                    self.switch_2.id: self.switch_2.as_dict(),
                    self.switch_3.id: self.switch_3.as_dict(),
                },
                "links": {
                    self.link_1_2.id: self.link_1_2.as_dict(),
                }
            }
        }

        url = f"{self.base_url}/"
        response = await self.api_client.get(url)
        assert response.status_code == 200
        assert response.json() == expected

        expected = {
            self.interface_1_1.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
            self.interface_2_1.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
            self.interface_3_1.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
            self.interface_1_2.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
            self.interface_2_2.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        url = f"{self.base_url}/interfaces/tag_ranges"
        response = await self.api_client.get(url)
        assert response.status_code == 200
        assert response.json() == expected

        expected = {
            self.link_1_2.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        url = f"{self.base_url}/links/tag_ranges"
        response = await self.api_client.get(url)
        assert response.status_code == 200
        assert response.json() == expected

    async def test_transfer_tags(self):
        """Test transferring tags from the link back to interfaces."""
        self.napp.controller.loop = asyncio.get_running_loop()

        payload = {
            "tag_type": "vlan",
            "tag_ranges": [],
        }
        url = f"{self.base_url}/links/{self.link_1_2.id}/tag_ranges"
        response = await self.api_client.post(
            url,
            json=payload
        )
        assert response.status_code == 200

        payload = {
            "tag_type": "vlan",
            "tag_ranges": [[1, 4094]],
        }
        url = f"{self.base_url}/interfaces/{self.interface_1_2.id}/tag_ranges"
        response = await self.api_client.post(
            url,
            json=payload
        )
        assert response.status_code == 200

        payload = {
            "tag_type": "vlan",
            "tag_ranges": [[1, 4094]],
        }
        url = f"{self.base_url}/interfaces/{self.interface_2_2.id}/tag_ranges"
        response = await self.api_client.post(
            url,
            json=payload
        )
        assert response.status_code == 200

        url = f"{self.base_url}/links/{self.link_1_2.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.link_1_2.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_1_2.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_1_2.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_2_2.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_2_2.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        assert data == expected

        payload = {
            "tag_type": "vlan",
            "tag_ranges": [],
        }
        url = f"{self.base_url}/interfaces/{self.interface_1_2.id}/tag_ranges"
        response = await self.api_client.post(
            url,
            json=payload
        )
        assert response.status_code == 200

        payload = {
            "tag_type": "vlan",
            "tag_ranges": [],
        }
        url = f"{self.base_url}/interfaces/{self.interface_2_2.id}/tag_ranges"
        response = await self.api_client.post(
            url,
            json=payload
        )
        assert response.status_code == 200

        payload = {
            "tag_type": "vlan",
            "tag_ranges": [[1, 4094]],
        }
        url = f"{self.base_url}/links/{self.link_1_2.id}/tag_ranges"
        response = await self.api_client.post(
            url,
            json=payload
        )
        assert response.status_code == 200

        #######

        url = f"{self.base_url}/links/{self.link_1_2.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.link_1_2.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_1_2.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_1_2.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_2_2.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_2_2.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        assert data == expected

    async def test_link_creation(self):
        """Test transferring tags to from interfaces to a new link."""
        # pylint: disable=attribute-defined-outside-init
        self.napp.controller.loop = asyncio.get_running_loop()

        self.interface_2_3 = Interface('s2-eth3', 3, self.switch_2)
        self.switch_2.update_interface(self.interface_2_3)

        self.interface_3_3 = Interface('s3-eth3', 3, self.switch_3)
        self.switch_3.update_interface(self.interface_3_3)

        url = f"{self.base_url}/interfaces/{self.interface_2_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_2_3.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_3_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_3_3.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        assert data == expected

        event = KytosEvent(
            'create_link',
            {
                "interface_a": self.interface_2_3,
                "interface_b": self.interface_3_3
            }
        )

        self.napp.add_links(event)

        new_link = self.interface_2_3.link

        assert new_link is not None

        self.link_2_3 = new_link

        url = f"{self.base_url}/links/{self.link_2_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.link_2_3.id: {
                "available_tags": {"vlan": [[1, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        data[self.link_2_3.id]["special_available_tags"]["vlan"] = set(
            data[self.link_2_3.id]["special_available_tags"]["vlan"]
        )
        data[self.link_2_3.id]["special_tags"]["vlan"] = set(
            data[self.link_2_3.id]["special_tags"]["vlan"]
        )
        data[self.link_2_3.id]["default_special_tags"]["vlan"] = set(
            data[self.link_2_3.id]["default_special_tags"]["vlan"]
        )

        expected[self.link_2_3.id]["special_available_tags"]["vlan"] = set(
            expected[self.link_2_3.id]["special_available_tags"]["vlan"]
        )
        expected[self.link_2_3.id]["special_tags"]["vlan"] = set(
            expected[self.link_2_3.id]["special_tags"]["vlan"]
        )
        expected[self.link_2_3.id]["default_special_tags"]["vlan"] = set(
            expected[self.link_2_3.id]["default_special_tags"]["vlan"]
        )

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_2_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_2_3.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_3_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_3_3.id: {
                "available_tags": {"vlan": []},
                "tag_ranges": {"vlan": []},
                "default_tag_ranges": {"vlan": []},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": []},
                "default_special_tags": {"vlan": []},
            },
        }

        assert data == expected

    async def test_link_creation_partial(self):
        """Test transferring tags to from interfaces to a new link."""
        # pylint: disable=attribute-defined-outside-init
        self.napp.controller.loop = asyncio.get_running_loop()

        self.interface_2_3 = Interface('s2-eth3', 3, self.switch_2)
        self.switch_2.update_interface(self.interface_2_3)

        self.interface_2_3.available_tags = {
            "vlan": [[1, 50], [101, 200], [301, 4094]]
        }

        self.interface_2_3.special_available_tags = {
            "vlan": ["untagged", "any"]
        }

        self.interface_3_3 = Interface('s3-eth3', 3, self.switch_3)
        self.switch_3.update_interface(self.interface_3_3)

        self.interface_3_3.available_tags = {
            "vlan": [[1, 100], [151, 200], [351, 4094]]
        }

        self.interface_3_3.special_available_tags = {
            "vlan": ["untagged"]
        }

        url = f"{self.base_url}/interfaces/{self.interface_2_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_2_3.id: {
                "available_tags": {"vlan": [[1, 50], [101, 200], [301, 4094]]},
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged", "any"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_3_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_3_3.id: {
                "available_tags": {
                    "vlan": [[1, 100], [151, 200], [351, 4094]]
                },
                "tag_ranges": {"vlan": [[1, 4094]]},
                "default_tag_ranges": {"vlan": [[1, 4094]]},
                "special_available_tags": {"vlan": ["untagged"]},
                "special_tags": {"vlan": ["untagged", "any"]},
                "default_special_tags": {"vlan": ["untagged", "any"]},
            },
        }

        assert data == expected

        event = KytosEvent(
            'create_link',
            {
                "interface_a": self.interface_2_3,
                "interface_b": self.interface_3_3
            }
        )

        self.napp.add_links(event)

        new_link = self.interface_2_3.link

        assert new_link is not None

        self.link_2_3 = new_link

        url = f"{self.base_url}/links/{self.link_2_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.link_2_3.id: {
                "available_tags": {"vlan": [[1, 50], [151, 200], [351, 4094]]},
                "tag_ranges": {"vlan": [[1, 50], [151, 200], [351, 4094]]},
                "default_tag_ranges": {
                    "vlan": [[1, 50], [151, 200], [351, 4094]]
                },
                "special_available_tags": {"vlan": ["untagged"]},
                "special_tags": {"vlan": ["untagged"]},
                "default_special_tags": {"vlan": ["untagged"]},
            },
        }

        data[self.link_2_3.id]["special_available_tags"]["vlan"] = set(
            data[self.link_2_3.id]["special_available_tags"]["vlan"]
        )
        data[self.link_2_3.id]["special_tags"]["vlan"] = set(
            data[self.link_2_3.id]["special_tags"]["vlan"]
        )
        data[self.link_2_3.id]["default_special_tags"]["vlan"] = set(
            data[self.link_2_3.id]["default_special_tags"]["vlan"]
        )

        expected[self.link_2_3.id]["special_available_tags"]["vlan"] = set(
            expected[self.link_2_3.id]["special_available_tags"]["vlan"]
        )
        expected[self.link_2_3.id]["special_tags"]["vlan"] = set(
            expected[self.link_2_3.id]["special_tags"]["vlan"]
        )
        expected[self.link_2_3.id]["default_special_tags"]["vlan"] = set(
            expected[self.link_2_3.id]["default_special_tags"]["vlan"]
        )

        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_2_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_2_3.id: {
                "available_tags": {"vlan": [[101, 150], [301, 350]]},
                "tag_ranges": {"vlan": [[51, 150], [201, 350]]},
                "default_tag_ranges": {"vlan": [[51, 150], [201, 350]]},
                "special_available_tags": {"vlan": ["any"]},
                "special_tags": {"vlan": ["any"]},
                "default_special_tags": {"vlan": ["any"]},
            },
        }
        assert data == expected

        url = f"{self.base_url}/interfaces/{self.interface_3_3.id}/tag_ranges"
        response = await self.api_client.get(
            url
        )
        assert response.status_code == 200
        data = response.json()

        expected = {
            self.interface_3_3.id: {
                "available_tags": {"vlan": [[51, 100]]},
                "tag_ranges": {"vlan": [[51, 150], [201, 350]]},
                "default_tag_ranges": {"vlan": [[51, 150], [201, 350]]},
                "special_available_tags": {"vlan": []},
                "special_tags": {"vlan": ["any"]},
                "default_special_tags": {"vlan": ["any"]},
            },
        }

        assert data == expected
