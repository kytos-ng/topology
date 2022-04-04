"""This test suite cover the db models, however, most have been
indirectly tested on test_main.py, so for now it's mostly to cover
the remaning parts."""

from datetime import datetime

from napps.kytos.topology.db.models import DocumentBaseModel, SwitchDoc


def test_document_base_model_dict() -> None:
    """test_document_base_model_dict."""
    _id = "some_id"
    utcnow = datetime.utcnow()
    payload = {"_id": _id, "inserted_at": utcnow, "updated_at": utcnow}
    model = DocumentBaseModel(**payload)
    assert model.dict() == {**payload, **{"id": _id}}
    assert "_id" not in model.dict(exclude={"_id"})


def test_switch_doc_preset_interfaces() -> None:
    """test_switch_doc_preset_interfaces."""
    dpid = "00:00:00:00:00:00:00:01"
    interface_id = f"{dpid}:1"
    interfaces = {
        interface_id: {
            "id": interface_id,
            "port_number": 1,
            "lldp": True,
            "enabled": True,
            "active": True,
            "mac": "some_mac",
            "speed": 0,
            "name": "some_name",
            "switch": dpid,
        }
    }
    payload = {
        "_id": dpid,
        "enabled": True,
        "active": True,
        "interfaces": interfaces,
    }
    model = SwitchDoc(**payload)
    assert model
    assert interface_id == model.interfaces[0].id


def test_switch_doc_no_preset_interfaces() -> None:
    """test_switch_doc_no_preset_interfaces."""
    dpid = "00:00:00:00:00:00:00:01"
    interfaces = []
    payload = {
        "_id": dpid,
        "enabled": True,
        "active": True,
        "interfaces": interfaces,
    }
    model = SwitchDoc(**payload)
    assert model
    assert model.interfaces == interfaces
