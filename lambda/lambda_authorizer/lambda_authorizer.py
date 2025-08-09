import os
import json
import logging
import jwt

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get('REGION')
USERPOOL_ID = os.environ.get('USERPOOL_ID')

def handler(event, context):
    logger.info("Authorizer ejecutándose")
    logger.info(f"Event: {json.dumps(event)}")

    token = event.get('authorizationToken')
    if not token:
        logger.error("Token no recibido")
        raise Exception("Unauthorized")

    # Remove the Bearer prefix if present
    if token.startswith("Bearer "):
        token = token.split(" ", 1)[1]

    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        logger.info(f"Payload decodificado: {decoded}")
        grupos = decoded.get('cognito:groups', [])
        logger.info(f"Grupos: {grupos}")

        if 'recruiters' in grupos:
            return generate_policy(decoded['sub'], "Allow", event['methodArn'])
        else:
            return generate_policy(decoded['sub'], "Deny", event['methodArn'])

    except Exception as e:
        logger.error(f"Error al procesar token: {e}")
        raise Exception("Unauthorized")


def generate_policy(principal_id, effect, resource):
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{
                "Action": "execute-api:Invoke",
                "Effect": effect,
                "Resource": resource
            }]
        }
    }
