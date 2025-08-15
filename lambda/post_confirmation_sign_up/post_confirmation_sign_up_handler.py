import boto3

def lambda_handler(event, context):
    user_pool_id = event['userPoolId']
    user_name = event['userName']
    user_attributes = event['request']['userAttributes']
    user_type = user_attributes.get('custom:userType')

    client = boto3.client('cognito-idp')

    # Map userType to group
    group_name = None
    match user_type:
        case 'recruiter':
            group_name = 'recruiters'
        case 'candidate':
            group_name = 'candidates'
        case _:
            print(f'Error: Tipo de usuario desconocido: {user_type}')
            raise Exception('Tipo de usuario desconocido')

    if group_name:
        try:
            client.admin_add_user_to_group(
                UserPoolId=user_pool_id,
                Username=user_name,
                GroupName=group_name
            )
            print(f'Usuario {user_name} agregado al grupo {group_name}')
        except Exception as e:
            print(f'Error agregando usuario al grupo: {e}')
            raise e

    return event
