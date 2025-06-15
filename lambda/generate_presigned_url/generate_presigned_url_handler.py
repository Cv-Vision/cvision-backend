import json
import boto3
import os
import re

s3 = boto3.client('s3')
BUCKET_NAME = os.environ.get("BUCKET_NAME", "cvision-cv-bucket")

# CORS headers configuration
# Note: In production, replace the Origin with our actual domain
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"  # 24 hours
}


def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', name)

def lambda_handler(event, context):
    # Handle preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            "statusCode": 204,  # No content for OPTIONS
            "headers": CORS_HEADERS,
            "body": ""
        }

    # Get user_id from Cognito claims
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized"})
        }

    try:
        # Parse the incoming event to get the body
        body = json.loads(event.get('body', '{}'))

        print("DEBUG EVENT:", event)
        print("DEBUG BODY:", body)

        job_id = body.get("job_id")
        filenames = body.get("filenames")  # We expect an array of filenames

        if not job_id or not filenames or not isinstance(filenames, list):
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Se requiere job_id y un array de filenames"})
            }

        # TODO: Validar job_id contra DynamoDB

        result = []
        for filename in filenames:
            safe_filename = sanitize_filename(filename)
            key = f"uploads/{job_id}/{safe_filename}"
            url = s3.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': key,
                    'ContentType': 'application/pdf'
                },
                ExpiresIn=3600
            )
            result.append({
                "filename": filename,
                "sanitized_filename": safe_filename,
                "upload_url": url,
                "s3_key": key
            })

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "job_id": job_id,
                "presigned_urls": result
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }

