"""Settings for the Topology NApp."""

# Set this option to true if you need the topology with bi-directional links
# DISPLAY_FULL_DUPLEX_LINKS = True

# Time (in seconds) to wait before setting a link as up
LINK_UP_TIMER = 10

# Base URL of the Flow Manager endpoint
FLOW_MANAGER_URL = "http://localhost:8181/api/kytos/flow_manager/v2"

# This is for checking link active state consistency with its interfaces.
# It's recommended that CONSISTENCY_INTERVAL is greater than LINK_UP_TIMER
# and CONSISTENCY_MIN_COUNT is greater than 1 just so the standard link
# activation path has always a chance to run first
CONSISTENCY_INTERVAL = 15
CONSISTENCY_MIN_COUNT = 2
