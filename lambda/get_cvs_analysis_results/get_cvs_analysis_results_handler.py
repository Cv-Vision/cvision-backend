import json
import os
import boto3

# Import ORM session handler and models
from db_handler import get_session
from models import JobPosting, CVAnalysisResult
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    # Handle preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            "statusCode": 204,
            "headers": CORS_HEADERS,
            "body": ""
        }

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized"})
        }

    # Extract job_id from query string
    job_id = event.get("queryStringParameters", {}).get("job_id")
    if not job_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Missing job_id"})
        }

    # Get a database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        # Verify that the job_id belongs to this user
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "You do not own this job posting"})
            }

        # Fetch CV analysis results from DB
        results = session.query(CVAnalysisResult).filter(
            CVAnalysisResult.job_posting_id == job_id
        ).all()

        formatted = [
            {
                # Access attributes directly from the ORM object
                "analysis_id": str(item.analysis_id),
                "job_id": item.job_posting_id,
                "name": item.analysis_data.get("name"),
                "score": item.analysis_data.get("score"),
                "reasons": item.analysis_data.get("reasons", []),
                "created_at": item.generated_at.isoformat() if item.generated_at else None
            }
            for item in results
        ]

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps(formatted)
        }

    except Exception as e:
        print("❌ Error fetching results:", str(e))
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Error fetching results: {str(e)}"})
        }
    finally:
        session.close()