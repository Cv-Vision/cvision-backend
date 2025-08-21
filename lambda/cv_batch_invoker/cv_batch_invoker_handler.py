import json
import boto3
import os
from botocore.exceptions import ClientError
from db_handler import get_session
from models import JobPosting
from sqlalchemy.orm.exc import NoResultFound

# --- Boto3 Clients ---
s3 = boto3.client("s3")
sqs = boto3.client("sqs")

# --- Environment Variables ---
bucket_name = os.environ.get("BUCKET")
table_name = os.environ.get("DYNAMODB_TABLE_NAME")
sqs_queue_url = os.environ.get("SQS_QUEUE_URL")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"  # 24 hours
}
def lambda_handler(event, context):
    """
    This function is triggered by an API Gateway request. It validates the user and job_id,
    lists all corresponding files in S3, and creates a task for each file in a DynamoDB table
    with a 'PENDING' status. It responds immediately with a 202 Accepted status.
    """
    print(f"Received event: {event}")
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized"})
        }

    # --- Parse and validate request body ---
    try:
        body = json.loads(event.get("body", "{}"))
        job_id = body.get("job_id")
        if not job_id:
            raise ValueError("job_id is a required field.")
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Invalid request body: {str(e)}"}),
        }

    # --- Verify job_id belongs to the user ---
    session = get_session()
    try:
        print(f"Verifying ownership of job_id '{job_id}' for user '{user_id}'...")
        # Use .one() to ensure exactly one result is found.
        # It raises NoResultFound if no job matches, which we catch.
        session.query(JobPosting).filter_by(
            posting_id=job_id,
            created_by_user_id=user_id
        ).one()
        print("Verification successful.")
    except NoResultFound:
        print("Verification failed: Job not found or does not belong to the user.")
        return {
            "statusCode": 404,  # used to hide whether a resource exists
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Job posting not found or you do not have permission to access it."}),
        }
    except Exception as e:
        # Catch other potential database errors (e.g., connection issues)
        print(f"A database error occurred during verification: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "An internal error occurred."}),
        }
    finally:
        # Always close the session to free up database connections
        session.close()

    prefix = f"uploads/{job_id}/"

    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        contents = response.get("Contents", [])
        # Filter out folder objects
        cv_files = [obj["Key"] for obj in contents if not obj["Key"].endswith("/")]

        if not cv_files:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "No files found for the specified job_id."}),
            }
    except ClientError as e:
        print(f"Error accessing S3: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Failed to list files from storage."}),
        }

    # --- Send tasks to SQS ---
    try:
        messages_sent_count = 0
        for cv_key in cv_files:
            message_body = {
                "job_id": job_id,
                "s3_key": cv_key,
            }
            sqs.send_message(
                QueueUrl=sqs_queue_url,
                MessageBody=json.dumps(message_body)
            )
            messages_sent_count += 1
        print(f"Successfully sent {messages_sent_count} messages to SQS for job_id {job_id}.")
    except ClientError as e:
        print(f"Error sending messages to SQS: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Failed to queue processing tasks."}),
        }

    # --- Respond to the client immediately ---
    return {
        "statusCode": 202,  # The request has been accepted for processing
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "message": "All CVs have been queued for immediate processing.",
            "job_id": job_id,
            "files_to_process": len(cv_files),
        }),
    }