"""Module to help to create Integration tests."""
from unittest.mock import Mock

from kytos.core import Controller
from kytos.core.config import KytosConfig
from kytos.core.connection import Connection, ConnectionState
from kytos.core.interface import Interface
from kytos.core.switch import Switch


def get_controller_mock():
    """Return a controller mock."""
    options = KytosConfig().options['daemon']
    controller = Controller(options)
    controller.log = Mock()
    return controller


def get_switch_mock(of_version, connection_state=ConnectionState.NEW,
                    dpid="00:00:00:00:00:00:00:01"):
    """Return a switch mock."""
    switch = Switch(dpid)
    address = Mock()
    port = Mock()
    socket = Mock()
    switch.connection = Connection(address, port, socket)
    switch.connection.protocol.version = of_version
    switch.connection.state = connection_state
    return switch


def get_interface_mock(interface_name, port, *args, **kwargs):
    """Return a interface mock."""
    switch = get_switch_mock(0x04)
    switch.connection = Mock()
    switch.connection.protocol.version = 0x04
    iface = Interface(interface_name, port, switch, *args, **kwargs)
    return iface
