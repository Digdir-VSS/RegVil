from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path
import json
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from config.utils import validate_initiell_prefill_data, transform_initiell_data_to_nested_with_prefill, get_status_date, get_initiell_date, get_oppstart_date

PREFILL_TRANSFORMERS = {
    "regvil-2025-initiell": transform_initiell_data_to_nested_with_prefill,
}

VALIDATE_TRANSFORMERS = {
    "regvil-2025-initiell": validate_initiell_prefill_data,
}

GET_DATES = {
    "regvil-2025-initiell": get_initiell_date,
    "regvil-2025-oppstart": get_oppstart_date,
    "regvil-2025-status": get_status_date,
}

@dataclass
class MaskinportenConfig:
    client_id: str
    scope: str
    kid: str

@dataclass
class AltinnClientConfig:
    environment: str
    base_app_url: str
    base_platfrom_url: str
    base_varsling_url: str
    application_owner_organisation: str

@dataclass
class MaskinportenEndpointsConfig:
    test: str
    prod: str
    ver1: str
    ver2: str

@dataclass
class APPConfig:
    app_name: Literal[
        "regvil-2025-initiell",
        "regvil-2025-status",
        "regvil-2025-oppstart",
        "regvil-2025-slutt"
    ]
    tag: dict[str, str] = field(default_factory=dict)
    dueBefore: str | None = None
    visibleAfter: str | None = None
    timedelta_visibleAfter: str | None = None
    timedelta_dueBefore: str | None = None
    emailSubject: str | None = None
    emailBody: str | None = None

    @classmethod
    def app_name(cls, app_name: str) -> "APPConfig":
        return cls(app_name=app_name)
    
    def get_date(self, report_data) -> str:
        get_date_fun = GET_DATES.get(self.app_name)
        if not get_date_fun:
            raise ValueError(f"No get date func defined for app: {self.app_name}")
        return get_date_fun(report_data, self.timedelta_visibleAfter)
    
    def get_prefill_data(self, data) -> dict:
        transformer = PREFILL_TRANSFORMERS.get(self.app_name)
        if not transformer:
            raise ValueError(f"No get prefill transformer defined for app: {self.app_name}")
        return transformer(data)
    
    def validate_prefill_data(self, data) -> dict:
        validator = VALIDATE_TRANSFORMERS.get(self.app_name)
        if not validator:
            raise ValueError(f"No validate prefill transformer defined for app: {self.app_name}")
        return validator(data)

class WorkflowDAG:
    def __init__(self, flow: dict[str, str]):
        self.flow = flow

    def get_next(self, current: str) -> str | None:
        return self.flow.get(current)

    def is_terminal(self, current: str) -> bool:
        return current not in self.flow

@dataclass
class APIConfig:
    maskinporten_config_instance: MaskinportenConfig
    maskinporten_config_varsling: MaskinportenConfig
    altinn_client: AltinnClientConfig
    maskinporten_endpoint: str
    secret_value: str
    workflow_dag: WorkflowDAG
    app_config:APPConfig

def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_full_config(base_path: Path, app_name: str, env: str) -> APIConfig:
    maskinporten_config_instance = MaskinportenConfig(**_load_json(base_path / env / "maskinporten_config_instance.json"))
    maskinporten_config_varsling = MaskinportenConfig(**_load_json(base_path / env / "maskinporten_config_varsling.json"))
    client_config = AltinnClientConfig(**_load_json(base_path / env / "config_client_file.json"))
    endpoints_config = MaskinportenEndpointsConfig(**_load_json(base_path / env /"maskinporten_endpoints.json"))
    workflow_dag = WorkflowDAG(_load_json(base_path / env / "workflow_DAG.json"))
    credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url="https://keyvaultvss.vault.azure.net/", credential=credential)
    secret_value = secret_client.get_secret("rapdigtest").value
    app_configs = _load_json(base_path / env / "app_config.json")

    return APIConfig(
        maskinporten_config_instance=maskinporten_config_instance,
        maskinporten_config_varsling=maskinporten_config_varsling,
        altinn_client=client_config,
        maskinporten_endpoint=getattr(endpoints_config, env),
        secret_value=secret_value,
        workflow_dag=workflow_dag,
        app_config=APPConfig(**app_configs[app_name])
    )