"""DB client."""

import os
from typing import Optional

from pymongo import MongoClient


def mongo_client(
    host_seeds=None,
    username=os.environ.get("MONGO_USERNAME")
    or os.environ.get("MONGO_INITDB_ROOT_USERNAME", ""),
    password=os.environ.get("MONGO_PASSWORD")
    or os.environ.get("MONGO_INITDB_ROOT_PASSWORD", ""),
    replicaset=os.environ.get("MONGO_REPLICASET"),
    connect=False,
    retrywrites=True,
    retryreads=True,
    maxpoolsize=int(os.environ.get("MONGO_MAX_POOLSIZE", 100)),
    minpoolsize=int(os.environ.get("MONGO_MIN_POOLSIZE", 10)),
    **kwargs,
) -> MongoClient:
    """mongo_client."""
    return MongoClient(
        host_seeds or ["localhost:27017"],
        username=username,
        password=password,
        connect=False,
        replicaset=replicaset,
        retrywrites=retrywrites,
        retryreads=retryreads,
        maxpoolsize=maxpoolsize,
        minpoolsize=minpoolsize,
        **kwargs,
    )


def bootstrap_index(
    db: MongoClient, collection: str, index: str, direction: int, **kwargs
) -> Optional[str]:
    """Bootstrap index."""
    indexes = set()

    for value in db[collection].index_information().values():
        if "key" not in value:
            pass
        if value["key"] and isinstance(value["key"], list):
            indexes.add(value["key"][0])

    if (index, direction) not in indexes:
        return db[collection].create_index([(index, direction)], **kwargs)

    return None
