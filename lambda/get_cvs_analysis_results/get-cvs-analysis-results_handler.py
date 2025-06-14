import boto3
import os
import json

dynamodb = boto3.resource('dynamodb')
cv_results_table = dynamodb.Table(os.environ['CV_ANALYSIS_RESULTS_TABLE'])
job_postings_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

def lambda_handler(event, context):
    # Get user_id from Cognito claims
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Unauthorized"})
        }

    # Extract job_id from query string
    job_id = event.get("queryStringParameters", {}).get("job_id")
    if not job_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Missing job_id"})
        }

    # Get user_id from Cognito claims
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Unauthorized"})
        }

    # Verify that the job_id belongs to this user
    try:
        response = job_postings_table.get_item(
            Key={"pk": f"JD#{job_id}", "sk": f"USER#{user_id}"}
        )
        if "Item" not in response:
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "You do not own this job posting"})
            }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed ownership check: {str(e)}"})
        }

    # Fetch CV analysis results from CVAnalysisResults table
    try:
        results = cv_results_table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": f"JOB#{job_id}"}
        )
        items = results.get("Items", [])
        formatted = [
            {
                "participant_id": item["participant_id"],
                "score": item.get("score"),
                "reasons": item.get("reasons", []),
                "created_at": item.get("created_at")
            }
            for item in items
        ]
        return {
            "statusCode": 200,
            "body": json.dumps(formatted),
            "headers": {"Content-Type": "application/json"}
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Error fetching results: {str(e)}"})
        }
