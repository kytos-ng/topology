"""Module to test the napp kytos/topology."""
import sys
import os
from pathlib import Path

if 'VIRTUAL_ENV' in os.environ:
    BASE_ENV = Path(os.environ['VIRTUAL_ENV'])
else:
    BASE_ENV = Path('/')

NAPPS_PATH = BASE_ENV / '/var/lib/kytos/napps/..'

sys.path.insert(0, str(NAPPS_PATH))
