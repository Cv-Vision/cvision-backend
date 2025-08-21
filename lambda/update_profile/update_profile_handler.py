import json
import logging
import os
import boto3
import base64
from datetime import datetime
import uuid
import sys

# Add the parent directory to sys.path to import modules from orm_layer
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from orm_layer.python.db_handler import get_db_session
from orm_layer.python.models import User, JobApplication

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
S3_BUCKET = os.environ.get('CV_BUCKET_NAME', 'cvision-cv-bucket')

def lambda_handler(event, context):
    """
    Handler for updating a user profile.
    Supports updating basic user information and CV upload.
    """
    try:
        logger.info('Received event: %s', json.dumps(event))
        
        # Check if authentication context is provided
        if 'requestContext' not in event or 'authorizer' not in event['requestContext']:
            return {
                'statusCode': 401,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Authentication required'})
            }
            
        # Get the user ID from Cognito authorizer
        claims = event['requestContext']['authorizer']['claims']
        user_id = claims.get('sub')
        
        if not user_id:
            return {
                'statusCode': 401,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Invalid authentication token'})
            }
            
        # Parse request body
        if 'body' not in event or not event['body']:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Request body is required'})
            }
            
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Invalid JSON in request body'})
            }
            
        # Get DB session
        session = get_db_session()
        
        try:
            # Get user from database
            user = session.query(User).filter(User.user_id == user_id).first()
            
            if not user:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'User not found'})
                }
                
            # Update basic user info if provided
            if 'name' in body:
                user.name = body['name']
                
            # Store additional profile data as needed
            # More fields can be added to the User model in the future
            
            # Handle CV file upload if provided
            if 'cvFile' in body and body['cvFile']:
                # Decode base64 file content
                try:
                    file_content = base64.b64decode(body['cvFile'].split(',')[1] if ',' in body['cvFile'] else body['cvFile'])
                except Exception as e:
                    logger.error(f"Error decoding CV file: {str(e)}")
                    return {
                        'statusCode': 400,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({'error': 'Invalid CV file format'})
                    }
                    
                # Generate a unique file key for S3
                file_key = f"cv/{user_id}/{str(uuid.uuid4())}.pdf"
                
                # Upload to S3
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=file_key,
                    Body=file_content,
                    ContentType='application/pdf'
                )
                
                # Update user's CV information
                # For now, we'll just store this in any existing applications
                # In a future enhancement, we could add a dedicated field to the User model
                applications = session.query(JobApplication).filter(JobApplication.user_id == user_id).all()
                for application in applications:
                    application.cv_upload_key = file_key
                    
                response_data = {
                    'message': 'Profile updated successfully',
                    'cvUploaded': True,
                    'user': {
                        'name': user.name,
                        'role': user.role
                    }
                }
            else:
                response_data = {
                    'message': 'Profile updated successfully',
                    'user': {
                        'name': user.name,
                        'role': user.role
                    }
                }
                
            # Commit changes to database
            session.commit()
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(response_data)
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error in update_profile: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }
