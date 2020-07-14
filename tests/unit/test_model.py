"""Module to test model class."""
from unittest import TestCase

from napps.kytos.topology.models import Host


class TestHost(TestCase):
    """Test the model class."""

    mac = "6e:c2:ea:c4:18:12"

    def test_as_dict(self):
        """Test as_dict."""
        host = Host(self.mac)
        expected = {'mac': self.mac, 'type': 'host'}
        self.assertEqual(host.as_dict(), expected)

    def test_id(self):
        """Test id."""
        host = Host(self.mac)
        self.assertEqual(host.id, self.mac)
