## `topology` scripts for Kytos version 2026.1.0

This folder contains Topology's related scripts:

### Remove <code>link_side</code> from DB/switches collections

[`000_remove_link_side.py`](./000_remove_link_side.py) is a script to remove unused `link_side` field from `switches` collections.


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

- The only following `CMD` command is available:

```
remove_link_side
```

#### Examples

- Remove every `link_side` field from every switch

```
CMD=remove_link_side python3 scripts/db/2026.1.0/000_remove_link_side.py
```

- The script will print messages similar to:

```
Switches found: 3
Switches modified: 0
```