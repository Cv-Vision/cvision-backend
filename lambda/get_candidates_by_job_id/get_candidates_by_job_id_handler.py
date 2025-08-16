import json
import os
import boto3

# Import ORM session handler and models
from db_handler import get_session
from models import JobPosting, JobApplication

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    # Handle CORS preflight request
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": CORS_HEADERS
        }

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Usuario no autenticado"})
        }

    # Get a database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        job_id = event.get("pathParameters", {}).get("job_id")
        if not job_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Falta job_id"})
            }

        # Verify that the user owns the job posting
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "No tienes permiso para ver esta información"})
            }

        # Query job applications for the given job_id
        applications = session.query(JobApplication).filter(
            JobApplication.job_posting_id == job_id
        ).all()

        candidates = []
        for app in applications:
            candidates.append({
                # Access attributes directly from the ORM object
                "application_id": str(app.application_id),
                "name": app.name,
                "cv_upload_key": app.cv_upload_key,
                "created_at": app.created_at.isoformat() if app.created_at else None,
                "score": app.score
            })

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps(
                {"job_id": job_id, "candidates": candidates}
            )
        }

    except Exception as e:
        print("❌ Error:", str(e))
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        session.close()