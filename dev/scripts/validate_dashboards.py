#!/usr/bin/env python
import json
import pathlib
import sys

import yaml


def main() -> None:
    errors = {}
    files = [pathlib.Path(file) for file in sys.argv[1:]]
    for file in files:
        try:
            yaml_data = yaml.safe_load(file.read_text())
        except yaml.error.YAMLError as yaml_exc:
            errors[file.name] = f"Error loading YAML: {yaml_exc}"
            continue

        try:
            dashboards = yaml_data["data"]
        except (KeyError, TypeError) as exc:
            errors[file.name] = f"Error getting 'data' field: {exc}"
            continue

        for dashboard in dashboards:
            try:
                json.loads(yaml_data["data"][dashboard])
            except (json.decoder.JSONDecodeError, TypeError) as exc:
                errors[file.name] = f"Error loading JSON data from '{dashboard}': {exc}"

    if errors:
        sys.exit("\n".join(f"{k}: {v}" for k, v in errors.items()))


if __name__ == "__main__":
    main()
