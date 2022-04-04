"""DB client."""

import os
from typing import Optional

from pymongo import MongoClient


def mongo_client(
    host_seeds=os.environ.get(
        "MONGO_HOST_SEEDS", "mongo1:27017,mongo2:27018,mongo3:27019"
    ),
    username=os.environ.get("MONGO_USERNAME"),
    password=os.environ.get("MONGO_PASSWORD"),
    database=os.environ.get("MONGO_DBNAME", "napps"),
    connect=False,
    retrywrites=True,
    retryreads=True,
    readpreference='primaryPreferred',
    maxpoolsize=int(os.environ.get("MONGO_MAX_POOLSIZE", 100)),
    minpoolsize=int(os.environ.get("MONGO_MIN_POOLSIZE", 10)),
    **kwargs,
) -> MongoClient:
    """mongo_client."""
    return MongoClient(
        host_seeds.split(","),
        username=username,
        password=password,
        connect=False,
        authsource=database,
        retrywrites=retrywrites,
        retryreads=retryreads,
        readpreference=readpreference,
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
        if "key" in value and isinstance(value["key"], list):
            indexes.add(value["key"][0])

    if (index, direction) not in indexes:
        return db[collection].create_index([(index, direction)], **kwargs)

    return None
