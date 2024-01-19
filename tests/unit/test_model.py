"""Module to test model class."""

from napps.kytos.topology.models import Host


class TestHost:
    """Test the model class."""

    mac = "6e:c2:ea:c4:18:12"

    def test_as_dict(self):
        """Test as_dict."""
        host = Host(self.mac)
        expected = {'mac': self.mac, 'type': 'host'}
        assert host.as_dict() == expected

    def test_id(self):
        """Test id."""
        host = Host(self.mac)
        assert host.id == self.mac
