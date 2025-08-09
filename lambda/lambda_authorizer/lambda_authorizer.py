import json
import urllib.request
import jwt  # PyJWT
from jwt.algorithms import RSAAlgorithm

REGION = os.environ['REGION']
USER_POOL_ID = os.environ['USER_POOL_ID']
APP_CLIENT_ID = os.environ['APP_CLIENT_ID']

# Cache de claves públicas
jwks_url = f'https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json'
jwks = None

def get_jwks():
    global jwks
    if jwks is None:
        with urllib.request.urlopen(jwks_url) as response:
            jwks = json.loads(response.read())
    return jwks

def generate_policy(principal_id, effect, resource):
    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        }
    }

def lambda_handler(event, context):
    token = event.get('authorizationToken')
    if not token or not token.startswith('Bearer '):
        return generate_policy('user', 'Deny', event['methodArn'])

    token = token[len('Bearer '):]  # remove 'Bearer '

    try:
        jwks = get_jwks()
        headers = jwt.get_unverified_header(token)
        kid = headers['kid']
        key = None
        for jwk in jwks['keys']:
            if jwk['kid'] == kid:
                key = RSAAlgorithm.from_jwk(json.dumps(jwk))
                break
        if key is None:
            raise Exception('Public key not found in jwks')

        # Verify token and claims
        payload = jwt.decode(
            token,
            key=key,
            algorithms=['RS256'],
            audience=APP_CLIENT_ID,
            issuer=f'https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}'
        )

        groups = payload.get('cognito:groups', [])
        if 'recruiters' not in groups:
            return generate_policy(payload['sub'], 'Deny', event['methodArn'])

        return generate_policy(payload['sub'], 'Allow', event['methodArn'])

    except Exception as e:
        print(f'Authorization error: {e}')
        return generate_policy('user', 'Deny', event['methodArn'])
