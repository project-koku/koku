#!/usr/bin/env python
import json
import pathlib
import sys

import yaml


def main() -> None:
    dashboards_path = pathlib.Path(__file__).parent.parent.parent / "dashboards"
    errors = {}
    for file in dashboards_path.glob("*.yaml"):
        yaml_data = yaml.safe_load(file.read_text())
        for item in yaml_data["data"]:
            try:
                json.loads(yaml_data["data"][item])
            except json.decoder.JSONDecodeError as exc:
                errors[file.name] = exc

    if errors:
        sys.exit("\n".join(f"{k}: {v}" for k, v in errors.items()))


if __name__ == "__main__":
    main()
