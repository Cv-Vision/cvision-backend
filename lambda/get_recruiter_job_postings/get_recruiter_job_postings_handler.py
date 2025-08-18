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
    session = None
    try:
        print("🔍 Event:", event)
        print("🔍 User ID:", user_id)
        print("🔍 Attempting to get database session...")

        session = get_session()
        if session is None:
            print("❌ Database session is None")
            raise Exception("Failed to establish database session")

        print("✅ Database session established successfully")
        print("🔍 Starting database query...")

        # Query all job postings for the user
        job_postings = session.query(JobPosting).filter(
            JobPosting.created_by_user_id == user_id
        ).all()

        print(f"✅ Query completed. Found {len(job_postings)} job postings")

        # Format the results to return as JSON
        items = []
        print("🔍 Starting to format results...")

        for i, job in enumerate(job_postings):
            print(f"🔍 Processing job {i + 1}: {job.title if hasattr(job, 'title') else 'No title'}")
            try:
                job_dict = {
                    "posting_id": str(job.posting_id),
                    "created_by_user_id": job.created_by_user_id,
                    "title": job.title,
                    "company": job.company,
                    "description": job.description,
                    "location": job.location,
                    "experience_level": job.experience_level.value if job.experience_level else None,
                    "english_level": job.english_level.value if job.english_level else None,
                    "contract_type": job.contract_type.value if job.contract_type else None,
                    "industry_experience": job.industry_experience,
                    "additional_requirements": job.additional_requirements,
                    "status": job.status.value if job.status else None,
                    "created_at": job.created_at.isoformat() if job.created_at else None
                }
                items.append(job_dict)
                print(f"✅ Job {i + 1} processed successfully")
            except Exception as job_error:
                print(f"❌ Error processing job {i + 1}: {str(job_error)}")
                raise job_error

        print("jobs found:", len(items))
        print("items found:", items)
        print("🔍 About to return response...")

        response = {
            "statusCode": 200,
            "body": json.dumps(items),
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
        }

        print("✅ Response created successfully")
        return response

    except Exception as e:
        print(f"Error in get_recruiter_job_postings: {str(e)}")
        if session is not None:
            session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
    finally:
        if session is not None:
            session.close()