from pathlib import Path
import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, EnvironmentCredential
import json
import pandas as pd

from collections.abc import Mapping, Sequence

def flatten_dict(d: Mapping, *, sep: str = ".") -> dict[str, object]:
    def _walk(obj, prefix: str | None, out: dict):
        # If it's a mapping, walk its items
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                key = f"{prefix}{sep}{k}" if prefix else str(k)
                _walk(v, key, out)
        # If it's a sequence (but not a string/bytes), index elements
        elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            for i, v in enumerate(obj):
                key = f"{prefix}{sep}{i}" if prefix else str(i)
                _walk(v, key, out)
        else:
            if prefix is None:
                raise TypeError("Top-level object must be a mapping.")
            out[prefix] = obj

    result: dict[str, object] = {}
    _walk(d, None, result)
    return result

def connect_blob():
    try:
        load_dotenv()

        if os.getenv("AZURE_CLIENT_ID"):
            # print("Using EnvironmentCredential for local dev")
            credential = EnvironmentCredential()
        else:
            # print("Using DefaultAzureCredential (includes managed identity in Azure)")
            credential = DefaultAzureCredential()

        blob_service_client = BlobServiceClient(
            os.getenv("BLOB_STORAGE_ACCOUNT_URL"), credential=credential
        )
        container_client = blob_service_client.get_container_client(
            os.getenv("BLOB_CONTAINER_NAME")
        )

        return container_client

    except Exception as e:
        print(f"Error connecting to Azure Blob Storage: {e}")
        return None

def get_files_in_blob_folder(container_client, path_to_blob_folder: str):
    files = container_client.walk_blobs(path_to_blob_folder)
    return [file for file in files if "Downloaded" in file.name]

def read_blob(file):
    container_client = connect_blob()
    blob_client = container_client.get_blob_client(file)
    blob_data = blob_client.download_blob().readall()
    return json.loads(blob_data)

def get_skjema_type(file_name: str):
    full_file_name = file_name.split("/")[-1]
    prefix = full_file_name.split("_")[0]
    return prefix.split("-")[-1]

def get_create_new_file_name(blob_name, digi_id, skjema_type):
    full_file_name = blob_name.split("/")[-1]
    short_file_name = full_file_name.split("_")[1]
    return f"{short_file_name}_{digi_id}_{skjema_type}"

def group_file_names_by_tiltak(digi_ids_set, file_names):
    groups = []
    for id_ in digi_ids_set:
        group = [file_name for file_name in file_names if id_ in file_name]
        groups.append({"items": group, "latest": get_lastest_skjema_type(group), "id": id_})
    return groups

def get_lastest_skjema_type(items):
    STAGES = ("Initiell", "Oppstart", "Status", "Slutt")
    _ORDER = {s: i for i, s in enumerate(STAGES)}
    best_idx = -1
    for it in items:
        group_id = it.split("_")[-1]
        idx = _ORDER[group_id]
        if idx > best_idx:
            best_idx, best = idx, it
    return best

def main():
    mapping = {"initiell": "Initiell", "oppstart": "Oppstart", "status": "Status", "slutt": "Slutt"}
    path_to_data_folder = Path(__file__).parent / "data" / "answered_skjema"
    container_client = connect_blob()
    blob_names = get_files_in_blob_folder(container_client, "prod/event_log/")
    files = []
    digi_ids = []
    file_names = []
    for blob in blob_names:
        blob_client = container_client.get_blob_client(blob)
        skjema_data = blob_client.download_blob().readall()
        skjema_file = json.loads(skjema_data)
        skjema_type = mapping[get_skjema_type(blob.name)]
        digi_id = skjema_file["digitaliseringstiltak_report_id"]
        digi_ids.append(digi_id)
        file_name = get_create_new_file_name(blob.name, digi_id, skjema_type)
        file_names.append(file_name)
        flattend_file = flatten_dict(skjema_file["data"])
        #flattend_file = skjema_file["data"]
        files.append({"name": file_name, "type": skjema_type, "tiltak_id": digi_id, "file": flattend_file})
    
    relevent_files = {"Initiell": [], "Oppstart": [], "Status": [], "Slutt": []}
    groups = group_file_names_by_tiltak(set(digi_ids), file_names)
    relevant_file_names = [group["latest"] for group in groups]
    print(relevant_file_names)
    for relevent_file_name in relevant_file_names:
        gen_name, tiltak_id, skjema_type = relevent_file_name.split("_")
        file = [file["file"] for file in files if file["type"] == skjema_type and file["tiltak_id"] == tiltak_id]
        if file:
            relevent_files[skjema_type].append(file[0])

    for skjema_type, data in relevent_files.items():
        #with open(path_to_data_folder/ f"{skjema_type}_rapportering.json", "w", encoding="utf-8") as f:
        #    json.dump(data, f, ensure_ascii=False, indent=2)
        skjema_df = pd.DataFrame(data)
        skjema_df.to_csv(path_to_data_folder/ f"{skjema_type}_rapportering.csv", encoding="utf-8")

if __name__ == "__main__":
    main()