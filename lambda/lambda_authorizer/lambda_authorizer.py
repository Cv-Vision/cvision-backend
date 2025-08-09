import json
import logging
import jwt
import urllib.request
from jwt import PyJWKClient

REGION = 'us-east-2'  # Cambia por tu región
USERPOOL_ID = 'us-east-2_OYnSTUQJa'  # Cambia por tu user pool id
APP_CLIENT_ID = '7q9u97f4vklogma8e8vipfvb0d'  # Tu client id

logger = logging.getLogger()
logger.setLevel(logging.INFO)

jwks_url = f'https://cognito-idp.{REGION}.amazonaws.com/{USERPOOL_ID}/.well-known/jwks.json'
jwks_client = PyJWKClient(jwks_url)

def build_policy(principal_id, effect, method_arn):
    policy = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{
                "Action": "execute-api:Invoke",
                "Effect": effect,
                "Resource": method_arn
            }]
        }
    }
    return policy

def lambda_handler(event, context):
    token = event['authorizationToken']
    method_arn = event['methodArn']

    logger.info(f"Event: {json.dumps(event)}")

    if token.lower().startswith('bearer '):
        token = token[7:]  # sacamos 'Bearer '

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token).key

        # Validamos token, incluye verificación firma, issuer, audiencia
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=['RS256'],
            audience=APP_CLIENT_ID,
            issuer=f'https://cognito-idp.{REGION}.amazonaws.com/{USERPOOL_ID}'
        )
        logger.info(f"Payload decodificado: {payload}")

        # Extraemos grupos (puede no existir)
        groups = payload.get('cognito:groups', [])

        # Control básico: solo dejar pasar si está en grupo recruiter
        if 'recruiters' in groups:
            return build_policy(payload['sub'], 'Allow', method_arn)
        else:
            logger.warning(f"Usuario sin permisos: grupos {groups}")
            raise Exception('Unauthorized')

    except Exception as e:
        logger.error(f"Error al procesar token: {e}")
        raise Exception('Unauthorized')
