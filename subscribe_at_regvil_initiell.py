from typing import Any, Dict
from pathlib import Path
import json
import requests
from auth.exchange_token_funcs import exchange_token
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://keyvaultvss.vault.azure.net/", credential=credential)
secret = client.get_secret("regvilprod")
secret_value = secret.value

def subscribe_to_altinn_events(altinn_token: str, endpoint: str, source_filter: str, type_filter: str):
    url = "https://platform.altinn.no/events/api/v1/subscriptions"
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
    "kid":"regvil-app-TEST.2025-08-19",
    "client_id":"c5e82235-7bab-496e-b28c-751566a6f810",
    "scope":"altinn:serviceowner altinn:events.subscribe"
}
    token = exchange_token(maskinport_client ,secret_value,  maskinporten_endpoint)

    endpoint = "https://regvil-app.lemonforest-e288550d.norwayeast.azurecontainerapps.io/httppost"
    for source_filter in ["https://digdir.apps.altinn.no/digdir/regvil-2025-initiell", "https://digdir.apps.altinn.no/digdir/regvil-2025-oppstart", "https://digdir.apps.altinn.no/digdir/regvil-2025-status", "https://digdir.apps.altinn.no/digdir/regvil-2025-slutt"]:
        type_filter = "app.instance.process.completed"
        print(token)
        response = subscribe_to_altinn_events(token, endpoint, source_filter, type_filter)
        print("Status Code:", response.status_code)
        print("Response:", response.text)
        response.raise_for_status()

if __name__ == "__main__":
    main()