## `topology` scripts

This folder contains Topology's related scripts:

<details><summary><h3>Data migration from <code>storehouse</code> to MongoDB</h3></summary>

[`storehouse_to_mongo.py`](./storehouse_to_mongo.py) is a script to migrate the data entries from certain namespaces from `storehouse` to MongoDB.

#### Pre-requisites

- There's no additional Python libraries dependencies required, other than installing the existing `topology`'s, or if you're running in development locally then installing `requirements/dev.in`
- Make sure you don't have `kytosd` running with otherwise topology will start writing to MongoDB, and the application could overwrite the data you're trying to insert with this script.
- Make sure MongoDB replica set is up and running.
- Export MongoDB related variables that [db/client.py](../db/client.py) uses, make sure the hosts names can be resolved:

```
export MONGO_USERNAME=
export MONGO_PASSWORD=
export MONGO_DBNAME=napps
export MONGO_HOST_SEEDS="mongo1:27017,mongo2:27018,mongo3:27099"
```

#### How to use

- Export these two environment variables, based on where storehouse and kytos are installed, if you're running `amlight/kytos:latest` docker image they should be:
 
```
export STOREHOUSE_NAMESPACES_DIR=/var/tmp/kytos/storehouse/
export PYTHONPATH=/var/lib/kytos
```

- Parametrize the environment variable `CMD` command and execute `storehouse_to_mongo.py` script (the command is passed via an env var to avoid conflicts with `kytosd`, since depending how you set the `PYTHONPATH` it can interfere)

- The following `CMD` commands are available:

```
insert_links_metadata
insert_switches_metadata
insert_interfaces_metadata
insert_topology
load_topology
load_switches_metadata
load_interfaces_metadata
load_links_metadata
```

The `load_*` commands are meant to be used to double check what would actually be loaded, so it's encouraged to try out the load command to confirm the data can be loaded properly, and if they are, feel free to use any of the `insert_*` commands, which will rely internally on the load functions to the either insert or update the documents.

For example, to double check what would be loaded in the topology from storehouse namespace `kytos.topology.status`:

```
CMD=load_topology python3 scripts/storehouse_to_mongo.py
```

And then, to insert (or update) the entire topology:

```
CMD=insert_topology python3 scripts/storehouse_to_mongo.py
```

If the topology you're migrating has metadata saved on `kytos.topology.(switches|interfaces|links).metadata` namespaces, you'll also have to run these commands:

```
CMD=insert_links_metadata python3 scripts/storehouse_to_mongo.py
CMD=insert_switches_metadata python3 scripts/storehouse_to_mongo.py
CMD=insert_interfaces_metadata python3 scripts/storehouse_to_mongo.py
```

</details>

<details><summary><h3> <code>$unset active</code> from DB switches and links collections </h3></summary>


#### Pre-requisites

- There's no additional Python libraries dependencies required, other than installing the existing `topology`'s, or if you're running in development locally then installing `requirements/dev.in`
- Make sure you don't have `kytosd` running with otherwise topology will start writing to MongoDB, and the application could overwrite the data you're trying to insert with this script.
- Make sure MongoDB replica set is up and running.
- Export the following MongnoDB variables accordingly in case your running outside of a container

```
export MONGO_USERNAME=
export MONGO_PASSWORD=
export MONGO_DBNAME=napps
export MONGO_HOST_SEEDS="mongo1:27017,mongo2:27018,mongo3:27099"
```

- The following `CMD` commands are available:

```
aggregate_unset_links
unset_links
aggregate_unset_switches_and_intfs
unset_switches_and_intfs
```

It's recommended that you run the `"aggregated_*"` commands first, just so you can preview the resulting aggregation with similar `$unset` key values. If the results of the aggregation are looking coherent, then you can proceed with the `"unset_*"` commands

#### Examples

- Previewing aggregated changes on `links` collection:

```
❯ CMD=aggregate_unset_links python scripts/unset_active.py
Aggregating links $unset active and metadata[last_status_is_active|last_status_change|notified_up_at]
{'_id': '4d42dc0852278accac7d9df15418f6d921db160b13d674029a87cef1b5f67f30', 'enabled': True, 'endpoints': [{'id': '00:00:00:00:00:00:00:02:3'}, {'id': '00:00:00:00:00:00:00:03:2'}], 'id': '4d42dc0852278accac7d9df15418f6d921db160b13d674029a87cef1b5f67f30', 'inserted_at': datetime.datetime(2023, 6, 20, 19, 54, 51, 726000), 'metadata': {}, 'updated_at': datetime.datetime(2023, 6, 20, 20, 13, 53, 696000)}
{'_id': 'c8b55359990f89a5849813dc348d30e9e1f991bad1dcb7f82112bd35429d9b07', 'enabled': True, 'endpoints': [{'id': '00:00:00:00:00:00:00:01:4'}, {'id': '00:00:00:00:00:00:00:03:3'}], 'id': 'c8b55359990f89a5849813dc348d30e9e1f991bad1dcb7f82112bd35429d9b07', 'inserted_at': datetime.datetime(2023, 6, 20, 19, 54, 51, 730000), 'metadata': {}, 'updated_at': datetime.datetime(2023, 6, 20, 20, 13, 59, 707000)}
{'_id': '78282c4d5b579265f04ebadc4405ca1b49628eb1d684bb45e5d0607fa8b713d0', 'enabled': True, 'endpoints': [{'id': '00:00:00:00:00:00:00:01:3'}, {'id': '00:00:00:00:00:00:00:02:2'}], 'id': '78282c4d5b579265f04ebadc4405ca1b49628eb1d684bb45e5d0607fa8b713d0', 'inserted_at': datetime.datetime(2023, 6, 20, 19, 54, 51, 732000), 'metadata': {}, 'updated_at': datetime.datetime(2023, 6, 20, 20, 13, 53, 700000)}
```

- Running `$unset` to update many on `links` collection:

```
❯ CMD=unset_links python scripts/unset_active.py 
Trying to $unset links 'active' and metadata[last_status_is_active|last_status_change|notified_up_at]...
Modified 3 links objects
```

- Running `$unset` to update many on `links` collection again, but expecting no changes:

```
❯ CMD=unset_links python scripts/unset_active.py
Trying to $unset links 'active' and metadata[last_status_is_active|last_status_change|notified_up_at]...
Modified 0 links objects
```

- Previewing aggregated changes on `switches` collection:

```
❯ CMD=aggregate_unset_switches_and_intfs python scripts/unset_active.py
Aggregating switches and interfaces $unset active
{'_id': '00:00:00:00:00:00:00:03', 'connection': '127.0.0.1:53680', 'data_path': 's3', 'enabled': True, 'hardware': 'Open vSwitch', 'id': '00:00:00:00:00:00:00:03', 'inserted_at': datetime.datetime(2023, 6, 20, 19, 54, 50, 467000), 'interfaces': [{'id': '00:00:00:00:00:00:00:03:4294967294', 'enabled': True, 'mac': 'c2:9d:dd:f0:f1:4f', 'speed': 0.0, 'port_number': 4294967294, 'name': 's3', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:03', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:03:1', 'enabled': True, 'mac': '6a:79:35:c4:9b:a3', 'speed': 1250000000.0, 'port_number': 1, 'name': 's3-eth1', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:03', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:03:2', 'enabled': True, 'mac': '2a:db:cc:f6:40:a0', 'speed': 1250000000.0, 'port_number': 2, 'name': 's3-eth2', 'nni': True, 'lldp': True, 'switch': '00:00:00:00:00:00:00:03', 'link': '4d42dc0852278accac7d9df15418f6d921db160b13d674029a87cef1b5f67f30', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:03:3', 'enabled': True, 'mac': '86:62:23:d9:7e:06', 'speed': 1250000000.0, 'port_number': 3, 'name': 's3-eth3', 'nni': True, 'lldp': True, 'switch': '00:00:00:00:00:00:00:03', 'link': 'c8b55359990f89a5849813dc348d30e9e1f991bad1dcb7f82112bd35429d9b07', 'link_side': None, 'metadata': {}, 'updated_at': None}], 'manufacturer': 'Nicira, Inc.', 'metadata': {}, 'ofp_version': '0x04', 'serial': 'None', 'software': '3.1.1', 'updated_at': datetime.datetime(2023, 6, 20, 20, 14, 48, 360000)}
{'_id': '00:00:00:00:00:00:00:02', 'connection': '127.0.0.1:53696', 'data_path': 's2', 'enabled': True, 'hardware': 'Open vSwitch', 'id': '00:00:00:00:00:00:00:02', 'inserted_at': datetime.datetime(2023, 6, 20, 19, 54, 50, 469000), 'interfaces': [{'id': '00:00:00:00:00:00:00:02:4294967294', 'enabled': True, 'mac': '7e:93:b8:64:eb:47', 'speed': 0.0, 'port_number': 4294967294, 'name': 's2', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:02', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:02:1', 'enabled': True, 'mac': '5a:e7:1b:02:f3:c3', 'speed': 1250000000.0, 'port_number': 1, 'name': 's2-eth1', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:02', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:02:2', 'enabled': True, 'mac': '32:75:61:02:93:a7', 'speed': 1250000000.0, 'port_number': 2, 'name': 's2-eth2', 'nni': True, 'lldp': True, 'switch': '00:00:00:00:00:00:00:02', 'link': '78282c4d5b579265f04ebadc4405ca1b49628eb1d684bb45e5d0607fa8b713d0', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:02:3', 'enabled': True, 'mac': 'ea:a0:51:8a:e5:70', 'speed': 1250000000.0, 'port_number': 3, 'name': 's2-eth3', 'nni': True, 'lldp': True, 'switch': '00:00:00:00:00:00:00:02', 'link': '4d42dc0852278accac7d9df15418f6d921db160b13d674029a87cef1b5f67f30', 'link_side': None, 'metadata': {}, 'updated_at': None}], 'manufacturer': 'Nicira, Inc.', 'metadata': {}, 'ofp_version': '0x04', 'serial': 'None', 'software': '3.1.1', 'updated_at': datetime.datetime(2023, 6, 20, 20, 14, 48, 362000)}
{'_id': '00:00:00:00:00:00:00:01', 'connection': '127.0.0.1:53674', 'data_path': 's1', 'enabled': True, 'hardware': 'Open vSwitch', 'id': '00:00:00:00:00:00:00:01', 'inserted_at': datetime.datetime(2023, 6, 20, 19, 54, 50, 551000), 'interfaces': [{'id': '00:00:00:00:00:00:00:01:4294967294', 'enabled': True, 'mac': '42:42:fb:8f:2b:44', 'speed': 0.0, 'port_number': 4294967294, 'name': 's1', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:01', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:01:4', 'enabled': True, 'mac': '72:bb:4f:ad:1f:22', 'speed': 1250000000.0, 'port_number': 4, 'name': 's1-eth4', 'nni': True, 'lldp': True, 'switch': '00:00:00:00:00:00:00:01', 'link': 'c8b55359990f89a5849813dc348d30e9e1f991bad1dcb7f82112bd35429d9b07', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:01:1', 'enabled': True, 'mac': '22:2c:ae:78:ce:7d', 'speed': 1250000000.0, 'port_number': 1, 'name': 's1-eth1', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:01', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:01:2', 'enabled': True, 'mac': '72:5c:af:10:fe:05', 'speed': 1250000000.0, 'port_number': 2, 'name': 's1-eth2', 'nni': False, 'lldp': True, 'switch': '00:00:00:00:00:00:00:01', 'link': '', 'link_side': None, 'metadata': {}, 'updated_at': None}, {'id': '00:00:00:00:00:00:00:01:3', 'enabled': True, 'mac': '8e:d3:93:64:34:be', 'speed': 1250000000.0, 'port_number': 3, 'name': 's1-eth3', 'nni': True, 'lldp': True, 'switch': '00:00:00:00:00:00:00:01', 'link': '78282c4d5b579265f04ebadc4405ca1b49628eb1d684bb45e5d0607fa8b713d0', 'link_side': None, 'metadata': {}, 'updated_at': None}], 'manufacturer': 'Nicira, Inc.', 'metadata': {}, 'ofp_version': '0x04', 'serial': 'None', 'software': '3.1.1', 'updated_at': datetime.datetime(2023, 6, 20, 20, 14, 48, 359000)}
```

- Running `$unset` to update many on `switches` collection:

```
❯ CMD=unset_switches_and_intfs python scripts/unset_active.py
Trying to $unset switches and interfaces 'active'
Modified 3 switches objects
```

- Running `$unset` to update many on `switches` collection again, but expecting no changes:

```
❯ CMD=unset_switches_and_intfs python scripts/unset_active.py
Trying to $unset switches and interfaces 'active'
Modified 0 switches objects
```

</details>
