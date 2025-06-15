import boto3
import os
import json
import decimal

dynamodb = boto3.resource('dynamodb')
cv_results_table = dynamodb.Table(os.environ['CV_ANALYSIS_RESULTS_TABLE'])
job_postings_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Credentials": True
}

def lambda_handler(event, context):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized"})
        }

    job_id = event.get("queryStringParameters", {}).get("job_id")
    if not job_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Missing job_id"})
        }

    try:
        response = job_postings_table.get_item(
            Key={"pk": f"JD#{job_id}", "sk": f"USER#{user_id}"}
        )
        if "Item" not in response:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "You do not own this job posting"})
            }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Failed ownership check: {str(e)}"})
        }

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
            "headers": CORS_HEADERS,
            "body": json.dumps(formatted, default=decimal_default)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Error fetching results: {str(e)}"})
        }
