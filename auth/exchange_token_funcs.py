# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

from typing import Dict
import requests
import uuid
from jwcrypto import jwk, jwt
from datetime import datetime, timezone

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def get_maskinporten_token(audience: str, secret,  client: Dict[str, str]):
  kid = client["kid"]
  integration_id = client["client_id"]
  scope = client["scope"]
  maskinporten_token = audience + "token"
  timestamp = int(datetime.now(timezone.utc).timestamp())
  private_pem = jwk.JWK.from_json(secret).export_to_pem(private_key=True, password=None).decode('ascii')
  key = jwk.JWK.from_pem(data=bytes(private_pem, 'ascii'),)

  jwt_header = {
    'alg': 'RS256',
    'kid': kid
  }
  jwt_claims = {
    'aud': audience,
    'iss': integration_id,
    'scope': scope,
    'resource': 'https://api.samarbeid.digdir.no/api/v1/clients', 
    'iat': timestamp,
    'exp': timestamp+100,
    'jti': str(uuid.uuid4())
  }
  jwt_token = jwt.JWT(
    header = jwt_header,
    claims = jwt_claims,
  )

  jwt_token.make_signed_token(key)
  signed_jwt = jwt_token.serialize()

  body = {
    'grant_type': "urn:ietf:params:oauth:grant-type:jwt-bearer",
    'assertion': signed_jwt
  }

  res = requests.post(maskinporten_token, data=body)
  if res.status_code == 200:
    return res.json()["access_token"]
  else:
     return(res.status_code)  

def exchange_token(client: Dict[str, str], secret, maskinporten_endpoint):
  maskinport_token = get_maskinporten_token(maskinporten_endpoint, secret, client)
  if type(maskinport_token) != int:
     response_new = requests.get("https://platform.tt02.altinn.no/authentication/api/v1/exchange/maskinporten",
                              headers={"Authorization": f"Bearer {maskinport_token}"})
     if response_new.status_code == 200:
        return response_new.text
     else:
        return f"exchange_token error {response_new.status_code}"  
  else:
     return "get_maskinporten_token error"
  

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
