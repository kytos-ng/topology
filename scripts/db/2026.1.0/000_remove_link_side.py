import os
import sys
from kytos.core.db import Mongo

def remove_link_side(mongo: Mongo):
    """Remove link_side field from every switche.interface."""
    db = mongo.client[mongo.db_name]
    result = db.switches.update_many(
        {},
        {
            "$unset": {
                "interfaces.$[].link_side": ""
            }
        }
    )
    print(f"Switches found: {result.matched_count}")
    print(f"Switches modified: {result.modified_count}")
    pass

if __name__ == "__main__":
    mongo = Mongo()
    db = mongo.client[mongo.db_name]
    cmds = {
        "remove_link_side": remove_link_side
    }
    try:
        cmd = os.environ["CMD"]
        command = cmds[cmd]
    except KeyError:
        print(
            f"Please set the 'CMD' env var. \nIt has to be one of these: {list(cmds.keys())}"
        )
        sys.exit(1)

    command(mongo)