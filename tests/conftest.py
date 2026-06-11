"""Shared test fixtures for BerkeleyTracker tests."""
import os
import tempfile

import pytest

from tracker.registry.db import TrackerDB


@pytest.fixture
def tmp_db():
    """Create a temporary TrackerDB for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = TrackerDB(path)
    yield db
    os.unlink(path)


# Sample SBS/BaseStation messages (MSG type 3 = airborne position)
SAMPLE_SBS_MESSAGES = [
    "MSG,3,1,1,A0B1C2,1,2024/01/15,12:30:00.000,2024/01/15,12:30:00.000,,35000,,,37.8751,-122.2697,,,,,,0",
    "MSG,1,1,1,A0B1C2,1,2024/01/15,12:30:01.000,2024/01/15,12:30:01.000,UAL1234,,,,,,,,,,,",
    "MSG,3,1,1,A3D4E5,1,2024/01/15,12:30:02.000,2024/01/15,12:30:02.000,,12500,,350,37.88,-122.27,,,0,0,0,0",
    "MSG,4,1,1,A0B1C2,1,2024/01/15,12:30:03.000,2024/01/15,12:30:03.000,,,450,,,,12345,,,,,",
]

# Sample AIS NMEA sentences
SAMPLE_AIS_NMEA = [
    # Type 1: Position report (class A)
    "!AIVDM,1,1,,B,13u@Dt002s000000000000000000,0*25",
    # Type 5: Static and voyage data
    "!AIVDM,2,1,3,B,55?MbV02>H97ac0000000000000000100000000000000P115@T206,0*1C",
    "!AIVDM,2,2,3,B,000000000000000,2*20",
]
