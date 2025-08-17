import boto3
from db_handler import get_session
from models import User

def lambda_handler(event, context):
    user_pool_id = event['userPoolId']
    user_name = event['userName']
    user_attributes = event['request']['userAttributes']
    user_type = user_attributes.get('custom:userType')
    user_id = user_attributes.get('sub')

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

    # Add user to the appropriate Cognito group
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

    # Create user in the database
    session = None
    try:
        session = get_session()
        existing_user = session.query(User).filter(User.user_id == user_id).first()
        if not existing_user:
            new_user = User(
                user_id=user_id,  # Cognito sub
                name=user_name,  # Name
                role=user_type.upper()
            )
            session.add(new_user)
            session.commit()
            print(f'Registro en DB creado para usuario {user_name}')
    except Exception as e:
        session.rollback()
        print(f'Error creando usuario en DB: {e}')
        raise e
    finally:
        session.close()

    return event
