from typing import Any, Dict
from pathlib import Path
import json
import requests
from auth.exchange_token_funcs import exchange_token
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://keyvaultvss.vault.azure.net/", credential=credential)
secret = client.get_secret("rapdigtest")
secret_value = secret.value

def subscribe_to_altinn_events(altinn_token: str, endpoint: str, source_filter: str, type_filter: str):
    url = "https://platform.tt02.altinn.no/events/api/v1/subscriptions"
    headers = {
       "Authorization": f"Bearer {altinn_token}",
       "Content-Type": "application/json"
    }
    data = {
       "endPoint": endpoint,
       "sourceFilter": source_filter,
       "typeFilter": type_filter,
    }
    resp = requests.post(url, headers=headers, json=data)
    return resp

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, 'r', encoding='utf-8') as file:
        return json.load(file)


def main():
    maskinporten_endpoints = load_in_json(Path(__file__).parent / "data" / "maskinporten_endpoints.json")
    test_config_client_file = load_in_json(Path(__file__).parent / "data" / "test_config_client_file.json")
    maskinporten_endpoint = maskinporten_endpoints[test_config_client_file["environment"]]

    maskinport_client = {
    "kid":"RapDig_maskinporten-TEST.2025-05-22",
    "client_id":"387ff46c-222f-412b-ab63-3abf0a2704bc",
    "scope":"altinn:serviceowner altinn:events.subscribe"
}
    token = exchange_token(maskinport_client ,secret_value,  maskinporten_endpoint)

    endpoint = "https://regvil-app.lemonforest-e288550d.norwayeast.azurecontainerapps.io/httppost"
    for app_name in ["regvil-2025-oppstart", "regvil-2025-status", "regvil-2025-slutt"]:
        source_filter = f"https://digdir.apps.tt02.altinn.no/digdir/{app_name}"
        type_filter = "app.instance.process.completed"
        response = subscribe_to_altinn_events(token, endpoint, source_filter, type_filter)
        print("Status Code:", response.status_code)
        print("Response:", response.text)
        response.raise_for_status()

if __name__ == "__main__":
    main()