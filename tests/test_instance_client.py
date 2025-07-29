from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import json
from typing import Dict, Any
import os
from dotenv import load_dotenv

from clients.instance_client import AltinnInstanceClient
from config.config_loader import load_full_config

load_dotenv()

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, "r", encoding="utf-8") as file:
        return json.load(file)

path_to_config_folder = Path(__file__).parent.parent / "config_files"
config = load_full_config(path_to_config_folder, "regvil-2025-initiell", os.getenv("ENV"))


credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value


def test_instance_created_found():
    """Test instance_created returns True when instance exists with matching report_id"""
    test_instance_client = AltinnInstanceClient.init_from_config(config)
    # Test with existing instance that should have the report_id
    result = test_instance_client.instance_created(
        "310075728",  # org_number
        "InitiellSkjemaLevert"  # report_id that should exist
    )
    
    assert result is True


def test_instance_created_not_found():
    """Test instance_created returns False when instance doesn't exist"""
    test_instance_client = AltinnInstanceClient.init_from_config(config)
    # Test with non-existing report_id
    result = test_instance_client.instance_created(
        "310075728",  # org_number
        "AnotherSkjemaLevert"  # report_id that shouldn't exist
    )
    
    assert result is False


def test_instance_created_different_org():
    """Test instance_created returns False when searching different organisation"""
    test_instance_client = AltinnInstanceClient.init_from_config(config)
    
    # Test with different org number
    result = test_instance_client.instance_created(
        "999999999",  # Different org_number  
        "InitiellSkjemaLevert"  # Same report_id
    )
    
    assert result is False