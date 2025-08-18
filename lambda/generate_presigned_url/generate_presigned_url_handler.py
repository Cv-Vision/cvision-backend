import json
import boto3
import os
import re
from db_handler import get_session
from enums import JobStatus
from models import JobPosting
from sqlalchemy import or_

s3 = boto3.client('s3')
bucket = os.environ["BUCKET"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', name)

def get_content_type(filename: str) -> str:
    ext = filename.lower().split('.')[-1]
    mapping = {
        "pdf": "application/pdf", # .pdf files
        "jpg": "image/jpeg", # .jpg files
        "jpeg": "image/jpeg", # .jpeg files
        "png": "image/png" # .png files
    }
    return mapping.get(ext, "application/octet-stream")

def validate_job_id(session, job_id, user_id):
    """
    New: Validates job_id against the PostgreSQL database.
    """
    try:
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            print("❌ Ownership or existence check failed.")
            return False

        # Check if the job is deleted
        if job_posting.status == JobStatus.DELETED:
            print("❌ Job status is DELETED.")
            return False

        print("✅ Ownership and status confirmed.")
        return True
    except Exception as e:
        print(f"Error when validating job_id against PostgreSQL: {e}")
        return False

def lambda_handler(event, context):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized"})
        }

    session = get_session()

    try:
        print("🔍 Event:", event)
        body = json.loads(event.get('body', '{}'))
        job_id = body.get("job_id")
        filenames = body.get("filenames")

        if not job_id or not filenames or not isinstance(filenames, list):
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Se requiere job_id y un array de filenames"})
            }

        # New: Validate job_id against PostgreSQL
        if not validate_job_id(session, job_id, user_id):
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "job_id no encontrado"})
            }

        result = []
        for filename in filenames:
            safe_filename = sanitize_filename(filename)
            content_type = get_content_type(safe_filename)
            key = f"uploads/{job_id}/{safe_filename}"
            url = s3.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': bucket,
                    'Key': key,
                    'ContentType': content_type,
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
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        session.close()