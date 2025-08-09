import json
import logging
import jwt
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Parámetros Cognito
REGION = 'us-east-2'  # Cambiá por tu región
USERPOOL_ID = 'us-east-2_OYnSTUQJa'  # Cambiá por tu user pool id
APP_CLIENT_ID = '7q9u97f4vklogma8e8vipfvb0d'  # Client ID

# URL para obtener JWKS públicos de Cognito
JWKS_URL = f'https://cognito-idp.{REGION}.amazonaws.com/{USERPOOL_ID}/.well-known/jwks.json'

# Grupos permitidos para acceso
ALLOWED_GROUPS = {'recruiters', 'candidates'}

# Cache JWKS para validar tokens
jwks = None

def get_jwks():
    global jwks
    if jwks is None:
        with urllib.request.urlopen(JWKS_URL) as response:
            jwks = json.loads(response.read())
    return jwks

def lambda_handler(event, context):
    logger.info(f'Evento recibido: {json.dumps(event)}')

    token = event.get('authorizationToken')
    if not token:
        logger.error('No se recibió token de autorización')
        raise Exception('Unauthorized')

    # El token viene con "Bearer " adelante, lo saco
    token = token.replace('Bearer ', '')

    try:
        jwks = get_jwks()
        # Validar el token (ver clave pública, algoritmo, issuer, audience)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header['kid']
        key = next((k for k in jwks['keys'] if k['kid'] == kid), None)

        if key is None:
            logger.error('Clave pública no encontrada en JWKS')
            raise Exception('Unauthorized')

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))

        payload = jwt.decode(
            token,
            public_key,
            algorithms=['RS256'],
            audience=APP_CLIENT_ID,
            issuer=f'https://cognito-idp.{REGION}.amazonaws.com/{USERPOOL_ID}'
        )

        logger.info(f'Payload decodificado: {payload}')

        # Verificar grupos permitidos
        user_groups = set(payload.get('cognito:groups', []))
        if not user_groups.intersection(ALLOWED_GROUPS):
            logger.warning(f'Usuario no pertenece a grupos permitidos: {user_groups}')
            raise Exception('Unauthorized')

        # Construir política para permitir acceso
        method_arn = event['methodArn']
        principal_id = payload['sub']

        policy = generate_policy(principal_id, 'Allow', method_arn)

        return policy

    except Exception as e:
        logger.error(f'Error al procesar token: {str(e)}')
        raise Exception('Unauthorized')


def generate_policy(principal_id, effect, resource):
    auth_response = {}
    auth_response['principalId'] = principal_id
    if effect and resource:
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        }
        auth_response['policyDocument'] = policy_document
    return auth_response
