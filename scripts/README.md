## Topology's scripts

This folder contains Topology's related scripts.

### Data migration from `storehouse` to MongoDB

[`storehouse_to_mongo.py`](./storehouse_to_mongo.py) is a script to migrate the data entries from certain namespaces from `storehouse` to MongoDB.

#### Pre-requisites

- There's no additional Python libraries dependencies required, other than installing the existing `topology`'s requirements-dev.txt file.
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

- Export these two environment variables, based on where storehouse and kytos is installed, if you're running `amlight/latest` docker image they should be:
 
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
CMD=load_topology python scripts/storehouse_to_mongo.py
```

And then, to insert (or update) the entire topology:

```
CMD=insert_topology python scripts/storehouse_to_mongo.py
```
