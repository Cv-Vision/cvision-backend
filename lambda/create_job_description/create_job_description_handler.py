import json
import uuid
from datetime import datetime
import boto3
import os
from enum import Enum

# === ENUM for job status ===
class JobStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"

# === ENUMS for structured requirements ===
class ExperienceLevel(str, Enum):
    JUNIOR = "JUNIOR"
    SEMISENIOR = "SEMISENIOR"
    SENIOR = "SENIOR"

class EnglishLevel(str, Enum):
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    NATIVE = "NATIVE"
    NOT_REQUIRED = "NOT_REQUIRED"

class ContractType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    FREELANCE = "FREELANCE"
    INTERNSHIP = "INTERNSHIP"

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

REQUIRED_FIELDS = ["title", "description"]

# CORS headers configuration
# Note: In production, replace the Origin with our actual domain
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"  # 24 hours
}

def lambda_handler(event, context):
    print("DEBUG EVENT:", json.dumps(event))
    try:
        # Verify that the event has a body
        if "body" not in event:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Missing request body"})
            }

        # Parse the body of the event
        try:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Invalid JSON in request body"})
            }

        # Validate required fields
        missing_fields = [field for field in REQUIRED_FIELDS if field not in body]
        if missing_fields:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": f"Missing fields: {', '.join(missing_fields)}"})
            }

        # Validate description is not empty
        if not body["description"].strip():
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Description cannot be empty"})
            }

        # Get user_id from the event
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        user_id = claims.get("sub")

        if not user_id:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Unauthorized - user_id not found"})
            }

        # Optional validated fields
        experience_level = body.get("experience_level")
        english_level = body.get("english_level")
        industry_experience = body.get("industry_experience")
        contract_type = body.get("contract_type")
        additional_requirements = body.get("additional_requirements")
        job_location = body.get("job_location")

        if experience_level is not None:
            try:
                ExperienceLevel(experience_level)
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid experience level value: {experience_level}"})}

        if english_level is not None:
            try:
                EnglishLevel(english_level)
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid English level value: {english_level}"})}

        if industry_experience is not None:
            if not isinstance(industry_experience, dict) or "required" not in industry_experience or not isinstance(
                    industry_experience["required"], bool):
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "Industry experience must include boolean 'required'"})}
            if industry_experience["required"]:
                if not industry_experience.get("industry") or not str(industry_experience.get("industry")).strip():
                    return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps(
                        {"message": "When industry experience is required, 'industry' must be provided"})}

        if contract_type is not None:
            try:
                ContractType(contract_type)
            except ValueError:
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid contract type value: {contract_type}"})}

        if job_location is not None:
            if not isinstance(job_location, str) or not job_location.strip():
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "Location must be a non-empty string"})}

        # Validate applicant_questions if present
        applicant_questions = body.get("applicant_questions")
        if applicant_questions is not None:
            if not isinstance(applicant_questions, list):
                return {"statusCode": 400, "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "applicant_questions must be a list"})}
            valid_types = {"YES_NO", "OPEN"}
            filtered_questions = []
            for q in applicant_questions:
                if not isinstance(q, dict):
                    continue
                text = q.get("text", "").strip()
                qtype = q.get("type")
                if text and qtype in valid_types:
                    filtered_questions.append({"text": text, "type": qtype})
            if filtered_questions:
                applicant_questions = filtered_questions
            else:
                applicant_questions = None

        # Generate unique job_id and created_at timestamp
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        # Build the item to be stored in DynamoDB
        item = {
            "pk": f"JD#{job_id}",
            "sk": f"USER#{user_id}",
            "created_at": created_at,
            "title": body["title"],
            "description": body["description"],
            "status": "ACTIVE",
        }

        # Attach optional fields if provided
        if experience_level is not None:
            item["experience_level"] = experience_level
        if english_level is not None:
            item["english_level"] = english_level
        if industry_experience is not None:
            item["industry_experience"] = industry_experience
        if contract_type is not None:
            item["contract_type"] = contract_type
        if additional_requirements is not None:
            item["additional_requirements"] = additional_requirements
        if job_location is not None:
            item["job_location"] = job_location
        if applicant_questions is not None:
            item["applicant_questions"] = applicant_questions

        # Save the item in DynamoDB
        table.put_item(Item=item)

        # Return the job_id as a response
        return {
            "statusCode": 201,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({"job_id": job_id})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Internal server error: {str(e)}"})
        }
