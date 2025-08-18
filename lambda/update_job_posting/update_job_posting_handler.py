import json
import os
from sqlalchemy import and_

# Import ORM session handler and models
from db_handler import get_session
from enums import JobStatus, ExperienceLevel, EnglishLevel, ContractType
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
            "body": json.dumps({"message": "Unauthorized - user_id not found"})
        }

    # Get a database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        job_id = event.get("pathParameters", {}).get("job-id")
        if not job_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Missing job_id in path parameters"})
            }

        body_str = event.get("body", "{}")
        body = json.loads(body_str) if body_str else {}

        if not body:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "At least one field must be provided for update"})
            }

        # Find the job posting and verify ownership
        job_posting = session.query(JobPosting).filter(
            and_(
                JobPosting.posting_id == job_id,
                JobPosting.created_by_user_id == user_id
            )
        ).first()

        if not job_posting:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": f"Job posting with ID {job_id} not found"})
            }

        # Validation logic
        if job_posting.status == JobStatus.DELETED:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Cannot modify a deleted job posting."})
            }

        # Update attributes directly from the body if they exist
        if "description" in body:
            new_description = body["description"]
            if not isinstance(new_description, str) or not new_description.strip():
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "Description cannot be empty or not a string"})}
            job_posting.description = new_description

        if "status" in body:
            new_status = body["status"]
            try:
                JobStatus(new_status)
                job_posting.status = new_status
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid status value: {new_status}"})}

        if "experience_level" in body:
            new_experience_level = body["experience_level"]
            try:
                ExperienceLevel(new_experience_level)
                job_posting.experience_level = new_experience_level
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid experience level value: {new_experience_level}"})}

        if "english_level" in body:
            new_english_level = body["english_level"]
            try:
                EnglishLevel(new_english_level)
                job_posting.english_level = new_english_level
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid English level value: {new_english_level}"})}

        if "job_location" in body:
            new_location = body["job_location"]
            if not isinstance(new_location, str) or not new_location.strip():
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "Location cannot be empty or not a string"})}
            job_posting.location = new_location

        if "industry_experience" in body:
            new_industry_experience = body["industry_experience"]
            if not isinstance(new_industry_experience, dict) or "required" not in new_industry_experience:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "Invalid industry_experience format"})}
            job_posting.industry_experience = new_industry_experience

        if "contract_type" in body:
            new_contract_type = body["contract_type"]
            try:
                ContractType(new_contract_type)
                job_posting.contract_type = new_contract_type
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid contract type value: {new_contract_type}"})}

        if "additional_requirements" in body:
            new_additional_requirements = body["additional_requirements"]
            if not isinstance(new_additional_requirements, dict):
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "additional_requirements must be an object"})}
            job_posting.additional_requirements = new_additional_requirements

        # Commit all changes in a single transaction
        session.commit()

        updated_item = {
            "posting_id": str(job_posting.posting_id),
            "created_by_user_id": job_posting.created_by_user_id,
            "title": job_posting.title,
            "description": job_posting.description,
            "location": job_posting.location,
            "company": job_posting.company,
            "experience_level": job_posting.experience_level,
            "english_level": job_posting.english_level,
            "contract_type": job_posting.contract_type,
            "industry_experience": job_posting.industry_experience,
            "additional_requirements": job_posting.additional_requirements,
            "status": job_posting.status,
            "created_at": job_posting.created_at.isoformat() if job_posting.created_at else None
        }

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "message": "Job posting updated successfully",
                "jobPosting": updated_item
            })
        }

    except Exception as e:
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Internal server error: {str(e)}"})
        }
    finally:
        session.close()