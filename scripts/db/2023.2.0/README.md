## `topology` scripts for Kytos version 2023.2.0

This folder contains Topology's related scripts:

<details><summary><h3>Change <code>tag_type</code> from integer to string type</h3></summary>

[`000_vlan_pool.py`](./000_vlan_pool.py) is a script to change ``available_vlans`` to ``available_tags``. Also adding new field ``tag_ranges``. These new fields have the type ``dict[str, list[list[int]]]``. Example

```
    available_tags = {"vlan": [[1, 299], [301, 4095]]}
    tag_ranges = {"vlan": [[1, 4095]]}
```

This scripts takes into account UNIs TAG (only integers) values as well.

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

#### How to use

- The following `CMD` commands are available:

```
aggregate_outdated_interfaces
update_database
```

`aggregate_outdated_interfaces` option is to see how many documents are going to be modified and how many are going to be added.

```
CMD=aggregate_outdated_interfaces python3 scripts/db/2023.2.0/000_vlan_pool.py
```

For the documents that are going to be modified, only the maximum and minimum value are going to be shown:

```
{'id': '00:00:00:00:00:00:00:01:3', 'max_number': 4095, 'min_number': 2}
```

For soon to be added documents, `avoid_tags` set is going to be shown representing the tags that are used and will need to be avoided in `available_tags`:

```
{'id': '00:00:00:00:00:00:00:01:1', 'avoid_tags': {200}}
```

A `WARNING` is going to be shown if a duplicated `TAG` is detected in different `EVC`s:

```
WARNING: Detected duplicated 200 TAG in EVCs 861a11d8fce148 and d74e18464d524b in interface 00:00:00:00:00:00:00:01:1
```

`update_database` updates and adds the required documents for compatability

```
CMD=update_database python3 scripts/db/2023.2.0/000_vlan_pool.py
```

The final messages will show how many documents have been modified and added

```
6 documents modified. 3 documents inserted
```

An `ERROR` can be shown if a duplicated `TAG` is detected in different `EVC`s. After this the pocess will exit without making any modification or adittion.

```
Error: Detected duplicated 200 TAG in EVCs 861a11d8fce148 and d74e18464d524b in interface 00:00:00:00:00:00:00:01:1
```

</details>

<details><summary><h3>Add <code>special_available_tags</code> and <code>special_tags</code> field to each Interface document in <code>interface_details</code> collection </h3></summary>

[`001_special_vlan_allocation.py`](./001_special_vlan_allocation.py) is to add the new field ``special_available_tags`` and ``special_tags`` to each interface document. This new field will keep track of special vlan usage:

```
special_available_tags = {"vlan": ["untagged"]}
special_tags = {"vlan": ["untagged", "any"]}
```

This scripts takes into account UNIs TAG values (only string) as well.

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

#### How to use

- The following `CMD` commands are available:

```
aggregate_outdated_interfaces
update_database
```

`aggregate_outdated_interfaces` option is to see how many documents are going to be modified and how many are going to be added.

```
CMD=aggregate_outdated_interfaces python3 scripts/db/2023.2.0/001_special_vlan_allocation.py
```

For the interfaces that are going to be modified, they are going to be listed:

```
There are 13 outdated interface documents which do not have 'special_available_tags' and/or 'special_tags' field:
00:00:00:00:00:00:00:02:3
```

`update_database` updates and adds the required documents for compatability

```
CMD=update_database python3 scripts/db/2023.2.0/001_special_vlan_allocation.py
```

The final messages will show how many interfaces have been modified:

```
1 interface was/were updated:
00:00:00:00:00:00:00:02:3
```

An `ERROR` can be shown if a duplicated `TAG` is detected in different `EVC`s. After this the pocess will exit without making any modification or adittion.

```
Error: Detected duplicated vlan 'any' TAG in EVCs d68eb033688a48 and 861a11d8fce148 in interface 00:00:00:00:00:00:00:01:1
```

</details>