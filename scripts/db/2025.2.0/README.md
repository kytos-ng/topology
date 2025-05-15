## `topology` scripts for Kytos version 2025.2.0

This folder contains Topology's related scripts:

### <code>$unset metadata</code> from DB switches and links collections

[`000_retire_metadata.py`](./000_retire_metadata.py) is a script to remove metadata from `interfaces`, `links`, and `switches`.


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
retire_link_metadata
retire_interface_metadata
retire_switch_metadata
```

- Use the `RETIRE_METADATA` variable to set the metadata to be retired. This should be a `:` separated list of metadata attributes to be removed.

#### Examples

- Retiring `last_status_is_active`, `last_status_change`, and `notified_up_at` from links:

```
❯ CMD=retire_link_metadata RETIRE_METADATA=last_status_is_active:last_status_change:notified_up_at ./000_retire_metadata.py
Trying to $unset link metadata[last_status_is_active|last_status_change|notified_up_at]...
Modified 18 link objects
```
