import json
from functools import lru_cache
from pathlib import Path


LOCATION_DATA_PATH = (
    Path(__file__).resolve().parent
    / "static"
    / "fleet"
    / "data"
    / "palawan_deployment_locations.json"
)


@lru_cache(maxsize=1)
def get_deployment_location_labels():
    with LOCATION_DATA_PATH.open(encoding="utf-8") as location_file:
        data = json.load(location_file)
    return frozenset(location["label"] for location in data["locations"])
