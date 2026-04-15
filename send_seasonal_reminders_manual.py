from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from config.config_loader import load_full_config
from send_warning import run as send_warning

load_dotenv()
credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def is_visible(instance: dict) -> bool:
    now = datetime.now(timezone.utc)
    current_year = now.year
    current_month = now.month

    if current_month in [4, 5, 6, 7, 8, 9]:
        threshold = datetime(current_year, 4, 1, tzinfo=timezone.utc)
    elif current_month in [10, 11, 12]:
        threshold = datetime(current_year, 10, 6, tzinfo=timezone.utc)
    else:  # [1, 2, 3]
        threshold = datetime(current_year - 1, 10, 6, tzinfo=timezone.utc)

    visible_after = instance.get("visibleAfter")
    if not visible_after:
        return False

    visible_after_dt = datetime.fromisoformat(visible_after.replace("Z", "+00:00"))
    return visible_after_dt <= threshold

def check_instance_active(instance_id, instance_meta, tag) -> bool:
    if instance_meta.get("isHardDeleted"):
        print(f"Instance {instance_id} is already hard deleted.")
        return False
    if instance_meta.get("isSoftDeleted"):
        print(f"Instance {instance_id} is soft deleted.")
        return False    
               
    if len(tag) == 0:
        print(f"Instance {instance_id} has no tag. Probably deleted.")
        return False
    return True 


def main() -> tuple[list, int]:
    print("Checking for instances that have not been answered")
    email_subject = "Status for tiltak i regjeringens digitaliseringsstrategi"
    email_body = "Hei, \n\nDu mottar denne e-posten fordi du er registrert som kontaktperson for ett eller flere tiltak i regjeringens digitaliseringsstrategi «Fremtidens digitale Norge – 2025 til 2030». \n\nDet er nå registrert at tiltaket din virksomhet er ansvarlig for, er i gang. Vi ber deg logge inn på Altinn.no for å rapportere status for fremdriften. Frist for rapportering er 14. april og 20 oktober. \n\nFormålet med rapporteringen er å sikre god oppfølging av strategien, og vurdere i hvilken grad målene nås. Informasjonen vil også danne grunnlag for bedre styring og samordning, samt bidra til å identifisere hindringer, avhengigheter og eventuelle behov for nye tiltak. \n\nTakk for at du bidrar i dette arbeidet \n\nVennlig hilsen \nDigitaliseringsdirektoratet"
    path_to_config_folder = Path(__file__).parent / "config_files"
    sent_reminders = []
    config = load_full_config(path_to_config_folder, "regvil-2025-status", os.getenv("ENV"))
    regvil_instance_client = AltinnInstanceClient.init_from_config(
            config,
        )
    print("Checking for instances that have not been answered")
    instance_ids = regvil_instance_client.fetch_instances_by_completion(instance_complete=False)
    for instance in instance_ids:
        partyID, instance_id = instance["instanceId"].split("/")
        inst_resp  = regvil_instance_client.get_instance(partyID, instance_id)
        if inst_resp.status_code != 200:
            continue

        instance_meta = inst_resp.json()
        instance_data = get_meta_data_info(instance_meta.get("data"))
        dataguid = instance_data.get("id")
        tag = instance_data.get("tags")

        print(instance_meta["visibleAfter"])
        if not is_visible(instance_meta):
            print(f"Instance {instance_id} is not yet visible. Skipping.")
            continue

        data_resp = regvil_instance_client.get_instance_data(partyID, instance_id, dataguid)
        if data_resp.status_code != 200:
            continue

        data = data_resp.json()
        if not check_instance_active(instance_id, instance_meta, tag):
            continue

        org_number = (
            data.get("Prefill")
                .get("AnsvarligVirksomhet")
                .get("Organisasjonsnummer")
            )
        dato = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(
                    f"Instance {instance_id} is created by the same user as last changed. Instance not answered."
                )
        file = {
                    "org_number": org_number,
                    "digitaliseringstiltak_report_id": tag[0],
                    "dato": dato,
                    "app_name": config.app_config.app_name,
                    "prefill_data": data,
                    "email_subject": email_subject,
                    "email_body": email_body
                }
        
        #send_warning(**file)
        sent_reminders.append({
                    "org_number": org_number,
                    "party_id": partyID,
                    "instance_id": instance_id,
                    "org_name":data.get("Prefill").get("AnsvarligVirksomhet").get("Navn"),
                    "digitaliseringstiltak_report_id": tag[0],
                    "dato": dato,
                    "app_name": config.app_config.app_name,
                })

if __name__ == "__main__":
    main()