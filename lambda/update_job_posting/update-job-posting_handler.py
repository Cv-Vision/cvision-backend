import boto3
import json
import os
import decimal
from enum import Enum


# Method to handle decimal serialization for JSON
def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError


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
        # Extract job_id from path parameters
        job_id = event.get("pathParameters", {}).get("job_id")
        if not job_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Missing job_id in path parameters"})
            }

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

        # Check if at least one field is provided for update
        if not any(key in body for key in ["description", "status", "experience_level",
                                           "english_level", "industry_experience",
                                           "contract_type", "additional_requirements"]):
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "At least one field must be provided for update"})
            }

        # Extract all fields from the request body
        new_description = body.get("description")
        new_status = body.get("status")
        new_experience_level = body.get("experience_level")
        new_english_level = body.get("english_level")
        new_industry_experience = body.get("industry_experience")
        new_contract_type = body.get("contract_type")
        new_additional_requirements = body.get("additional_requirements")

        # Validate description is not empty if provided
        if new_description is not None and not new_description.strip():
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Description cannot be empty"})
            }

        # Validate experience_level if provided
        if new_experience_level is not None:
            try:
                ExperienceLevel(new_experience_level)  # This will raise ValueError if invalid
            except ValueError:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"message": f"Invalid experience level value: {new_experience_level}"})
                }

        # Validate english_level if provided
        if new_english_level is not None:
            try:
                EnglishLevel(new_english_level)  # This will raise ValueError if invalid
            except ValueError:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"message": f"Invalid English level value: {new_english_level}"})
                }

        # Validate industry_experience if provided
        if new_industry_experience is not None:
            if not isinstance(new_industry_experience, dict):
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({
                                           "message": "Industry experience must be an object with 'required' and optional 'industry' fields"})
                }

            if "required" not in new_industry_experience or not isinstance(new_industry_experience["required"], bool):
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"message": "Industry experience must include a boolean 'required' field"})
                }

            if new_industry_experience["required"] and (
                    "industry" not in new_industry_experience or not new_industry_experience["industry"].strip()):
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {"message": "When industry experience is required, the 'industry' field must be provided"})
                }

        # Validate contract_type if provided
        if new_contract_type is not None:
            try:
                ContractType(new_contract_type)  # This will raise ValueError if invalid
            except ValueError:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"message": f"Invalid contract type value: {new_contract_type}"})
                }

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

            current_item = response["Item"]
            current_status = current_item.get("status", "ACTIVE")

            # Restriction logic based on current status
            # Determine which fields are being updated (excluding status)
            updating_fields = any([
                new_description is not None,
                new_experience_level is not None,
                new_english_level is not None,
                new_industry_experience is not None,
                new_contract_type is not None,
                new_additional_requirements is not None
            ])
            updating_status = new_status is not None

            if current_status == JobStatus.DELETED:
                return {
                    "statusCode": 403,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"message": "Cannot modify, add CVs, or change status of a deleted job posting."})
                }
            if current_status == JobStatus.CANCELLED:
                if updating_fields:
                    return {
                        "statusCode": 403,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"message": "Cannot modify or add CVs to a cancelled job posting. Only status change is allowed."})
                    }
            if current_status == JobStatus.INACTIVE:
                # Only restrict adding CVs, which is not handled here, so just a placeholder comment
                pass  # Field updates and status change are allowed
            if current_status == JobStatus.ACTIVE:
                pass  # All updates allowed

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

            # Add experience_level update if provided
            if new_experience_level is not None:
                update_parts.append("experience_level = :experience_level")
                expression_attribute_values[":experience_level"] = new_experience_level

            # Add english_level update if provided
            if new_english_level is not None:
                update_parts.append("english_level = :english_level")
                expression_attribute_values[":english_level"] = new_english_level

            # Add industry_experience update if provided
            if new_industry_experience is not None:
                update_parts.append("industry_experience = :industry_experience")
                expression_attribute_values[":industry_experience"] = new_industry_experience

            # Add contract_type update if provided
            if new_contract_type is not None:
                update_parts.append("contract_type = :contract_type")
                expression_attribute_values[":contract_type"] = new_contract_type

            # Add additional_requirements update if provided
            if new_additional_requirements is not None:
                update_parts.append("additional_requirements = :additional_requirements")
                expression_attribute_values[":additional_requirements"] = new_additional_requirements

            # Build the update expression
            update_expression = "SET " + ", ".join(update_parts)

            # Update the job posting
            update_params = {
                "Key": {
                    "pk": f"JD#{job_id}",
                    "sk": f"USER#{user_id}"
                },
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": expression_attribute_values,
                "ReturnValues": "ALL_NEW"
            }

            # Only include ExpressionAttributeNames if it's not empty
            if expression_attribute_names:
                update_params["ExpressionAttributeNames"] = expression_attribute_names

            update_response = table.update_item(**update_params)

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
