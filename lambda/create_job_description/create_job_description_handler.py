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
