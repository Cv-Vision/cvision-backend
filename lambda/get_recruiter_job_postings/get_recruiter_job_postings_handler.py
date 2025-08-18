import json
import os
import boto3

# Import ORM session handler and models
from db_handler import get_session
from models import JobPosting

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized - user_id not found"})
        }

    # Get a database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        # Query all job postings for the user
        job_postings = session.query(JobPosting).filter(
            JobPosting.created_by_user_id == user_id
        ).all()

        # Format the results to return as JSON
        items = []
        for job in job_postings:
            items.append({
                "posting_id": str(job.posting_id),
                "created_by_user_id": job.created_by_user_id,
                "title": job.title,
                "company": job.company,
                "description": job.description,
                "location": job.location,
                "experience_level": job.experience_level,
                "english_level": job.english_level,
                "contract_type": job.contract_type,
                "industry_experience": job.industry_experience,
                "additional_requirements": job.additional_requirements,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None
            })
        print("jobs found:", len(items))
        print("items found:", items)

        return {
            "statusCode": 200,
            "body": json.dumps(items),
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
        }
    except Exception as e:
        session.rollback()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
    finally:
        session.close()