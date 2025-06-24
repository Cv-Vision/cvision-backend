import json
import os
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime

# Initialize AWS resources
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

results_table = dynamodb.Table(os.environ["CV_ANALYSIS_RESULTS_TABLE"])
job_postings_table = dynamodb.Table(os.environ["JOB_POSTINGS_TABLE"])
job_applications_table = dynamodb.Table(os.environ["JOB_APPLICATIONS_TABLE"])
results_bucket = os.environ["RESULTS_BUCKET"]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS}

    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")
    if not job_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing job_id"})}

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    try:
        response = job_postings_table.get_item(Key={"pk": f"JD#{job_id}", "sk": f"USER#{user_id}"})
        if "Item" not in response:
            return {"statusCode": 403, "headers": CORS_HEADERS, "body": json.dumps({"message": "You do not own this job posting"})}
    except Exception as e:
        return {"statusCode": 500, "headers": CORS_HEADERS, "body": json.dumps({"error": f"Ownership check failed: {str(e)}"})}

    try:
        body = json.loads(event.get("body") or "{}")
        cv_ids = body.get("cv_ids", [])
        if not cv_ids:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing cv_ids in request body"})}

        deleted = []
        for cv_id in cv_ids:
            result_pk = f"RESULT#{job_id}"
            result_sk = f"RECRUITER#{user_id}#CV#{cv_id}"
            s3_key = f"results/{job_id}/{user_id}#{cv_id}.json"

            # Delete from CV_ANALYSIS_RESULTS_TABLE
            results_table.delete_item(Key={"pk": result_pk, "sk": result_sk})

            # Delete object from S3
            s3.delete_object(Bucket=results_bucket, Key=s3_key)

            # Remove cv_s3_key from JobApplications
            job_applications_table.update_item(
                Key={"pk": f"JD#{job_id}", "sk": f"CV#{cv_id}"},
                UpdateExpression="REMOVE cv_s3_key"
            )

            deleted.append(cv_id)

        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"message": "Deleted analysis results", "cv_ids": deleted})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Failed to delete results: {str(e)}"})
        }
