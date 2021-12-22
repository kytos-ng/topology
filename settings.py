"""Settings for the Topology NApp."""

# Set this option to true if you need the topology with bi-directional links
# DISPLAY_FULL_DUPLEX_LINKS = True

# Time (in seconds) to wait before setting a link as up
LINK_UP_TIMER = 10

# Time (in seconds) to wait for a confirmation from storehouse
# when retrieving or updating a box
STOREHOUSE_TIMEOUT = 5.0

# Time (in seconds) to sleep while waiting from storehouse (busy wait)
STOREHOUSE_WAIT_INTERVAL = 0.05
