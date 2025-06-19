import boto3
import json
import os
import decimal
from enum import Enum


# === ENUM for job status ===
class JobStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"


dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

# CORS headers configuration
# Note: In production, replace the Origin with our actual domain
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"  # 24 hours
}


# Method to handle decimal serialization for JSON
def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError

def lambda_handler(event, context):
    # Handle preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            "statusCode": 204,  # No content for OPTIONS
            "headers": CORS_HEADERS,
            "body": ""
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
        if "job_id" not in body:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Missing job_id field"})
            }

        # Check if at least one of description or status is provided
        if "description" not in body and "status" not in body:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "At least one of description or status must be provided"})
            }

        # Validate description is not empty if provided
        if "description" in body and not body["description"].strip():
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Description cannot be empty"})
            }

        job_id = body["job_id"]
        new_description = body.get("description")
        new_status = body.get("status")

        # Check if the job posting exists and belongs to the user
        try:
            response = table.get_item(
                Key={
                    "pk": f"JD#{job_id}",
                    "sk": f"USER#{user_id}"
                }
            )

            if "Item" not in response:
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"message": f"Job posting with ID {job_id} not found"})
                }

            # Prepare update expression and attribute values
            update_parts = []
            expression_attribute_values = {}
            expression_attribute_names = {}

            # Add description update if provided
            if new_description is not None:
                update_parts.append("description = :description")
                expression_attribute_values[":description"] = new_description

            # Add status update if provided
            if new_status is not None:
                # Validate status is a valid enum value
                try:
                    JobStatus(new_status)  # This will raise ValueError if invalid
                    update_parts.append("#status = :status")
                    expression_attribute_values[":status"] = new_status
                    expression_attribute_names["#status"] = "status"
                except ValueError:
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"message": f"Invalid status value: {new_status}"})
                    }

            # Build the update expression
            update_expression = "SET " + ", ".join(update_parts)

            # Update the job posting
            update_response = table.update_item(
                Key={
                    "pk": f"JD#{job_id}",
                    "sk": f"USER#{user_id}"
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ExpressionAttributeNames=expression_attribute_names if expression_attribute_names else None,
                ReturnValues="ALL_NEW"
            )

            updated_item = update_response.get("Attributes", {})

            return {
                "statusCode": 200,
                "headers": {
                    **CORS_HEADERS,
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "message": "Job posting updated successfully",
                    "jobPosting": updated_item
                }, default=decimal_default)
            }

        except Exception as e:
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": f"Error checking job posting: {str(e)}"})
            }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Internal server error: {str(e)}"})
        }