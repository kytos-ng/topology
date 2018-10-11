"""Most relevant classes to be used on the topology."""


__all__ = ('Host', 'Topology')


class Topology:
    """Represent the topology with links and switches."""

    def __init__(self, switches, links):
        """Create a instance of Topology."""
        self.switches = switches
        self.links = links


class Host:
    """Represents the Host."""

    def __init__(self, mac):
        """Create a instance of Host."""
        self.mac = mac

    @property
    def id(self):  # pylint: disable=invalid-name
        """Return the host id."""
        return self.mac

    def as_dict(self):
        """Return a dict representation of a Host."""
        return {'mac': self.mac,
                'type': 'host'}
