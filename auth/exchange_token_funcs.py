import requests
import uuid
from jwcrypto import jwk, jwt
from datetime import datetime, timezone
import logging


class MaskinportenTokenError(Exception):
    pass


class AltinnExchangeTokenError(Exception):
    pass


class MaskinportenTokenRequestError(Exception):
    """Raised when Maskinporten token request fails."""

    pass


def get_maskinporten_token(
    audience: str, secret: str, kid: str, client_id: str, scope: str
):
    maskinporten_token = audience + "token"
    timestamp = int(datetime.now(timezone.utc).timestamp())
    private_pem = (
        jwk.JWK.from_json(secret)
        .export_to_pem(private_key=True, password=None)
        .decode("ascii")
    )
    key = jwk.JWK.from_pem(
        data=bytes(private_pem, "ascii"),
    )

    jwt_header = {"alg": "RS256", "kid": kid}
    jwt_claims = {
        "aud": audience,
        "iss": client_id,
        "scope": scope,
        "resource": "https://api.samarbeid.digdir.no/api/v1/clients",
        "iat": timestamp,
        "exp": timestamp + 100,
        "jti": str(uuid.uuid4()),
    }
    jwt_token = jwt.JWT(
        header=jwt_header,
        claims=jwt_claims,
    )

    jwt_token.make_signed_token(key)
    signed_jwt = jwt_token.serialize()

    try:
        res = requests.post(
            maskinporten_token,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
            },
        )

        if res.status_code == 200:
            logging.info("Successfully received access token from Maskinporten")
            return res.json()["access_token"]
        else:
            logging.error(
                f"Token request failed: {res.status_code}, Response: {res.text}"
            )
            raise MaskinportenTokenRequestError(
                f"Failed to get token. Status: {res.status_code}, Response: {res.text}"
            )
    except requests.RequestException as e:
        logging.exception("HTTP error during Maskinporten token request")
        raise MaskinportenTokenRequestError(
            "HTTP request to Maskinporten failed"
        ) from e


def exchange_token(
    maskinporten_endpoint: str, secret: str, kid: str, client_id: str, scope: str
):
    maskinport_token = get_maskinporten_token(
        audience=maskinporten_endpoint,
        secret=secret,
        kid=kid,
        client_id=client_id,
        scope=scope,
    )
    try:
        response = requests.get(
            "https://platform.tt02.altinn.no/authentication/api/v1/exchange/maskinporten",
            headers={"Authorization": f"Bearer {maskinport_token}"},
        )
        response.raise_for_status()
        logging.info("Successfully exchanged token with Altinn")
        return response.text
    except requests.HTTPError as e:
        logging.error(
            f"Token exchange failed: {e.response.status_code} - {e.response.text}"
        )
        raise AltinnExchangeTokenError(
            f"Altinn token exchange failed: {e.response.status_code} - {e.response.text}"
        ) from e
    except requests.RequestException as e:
        logging.exception("HTTP request to Altinn failed")
        raise AltinnExchangeTokenError("Request to Altinn failed") from e
