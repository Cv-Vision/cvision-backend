import os
import json
import boto3
from botocore.exceptions import ClientError
from sqlalchemy import and_

# Import ORM session handler and models
from db_handler import get_session
from models import JobPosting, JobApplication

s3 = boto3.client("s3")
bucket = os.environ["BUCKET"]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,GET",
    "Access-Control-Allow-Credentials": "true"
}

def lambda_handler(event, context):
    # Preflight CORS
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "CORS OK"})
        }

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Unauthorized"})
        }

    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")
    cv_id = path_params.get("cv_id")

    if not job_id or not cv_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing job_id or cv_id"})
        }

    # Get a database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        # Validate ownership of the job posting with ORM
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Forbidden - Not your job posting"})
            }

        # Find the JobApplication to get the S3 key
        cv_item = session.query(JobApplication).filter(
            and_(
                JobApplication.job_posting_id == job_id,
                JobApplication.cv_hash == cv_id
            )
        ).first()

        if not cv_item or not cv_item.cv_upload_key:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "CV not found"})
            }

        upload_key = cv_item.cv_upload_key
        filename = cv_item.cv_hash  # Use the CV hash as filename

        # Generate presigned URL (15 min)
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": upload_key},
            ExpiresIn=900
        )

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "url": presigned_url,
                "filename": filename
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        session.close()