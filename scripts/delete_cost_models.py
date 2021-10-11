from os import environ

import requests

if __name__ == "__main__":
    koku_host = environ.get("KOKU_API_HOSTNAME")
    koku_port = environ.get("KOKU_PORT")
    url = f"http://{koku_host}:{koku_port}/api/cost-management/v1/cost-models/"

    r = requests.get(url).json()
    cost_model_uuids = []
    for model in r.get("data", []):
        cost_model_uuid = model.get("uuid")
        if cost_model_uuid:
            cost_model_uuids.append(cost_model_uuid)

    for cost_model_uuid in cost_model_uuids:
        delete_url = url + f"{cost_model_uuid}/"
        print(f"Calling {delete_url}")
        r = requests.delete(delete_url)
        print(r)
