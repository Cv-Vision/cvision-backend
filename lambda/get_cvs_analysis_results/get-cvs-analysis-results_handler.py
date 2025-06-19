import boto3
import os
import json
import decimal

# Initialize DynamoDB resources
dynamodb = boto3.resource('dynamodb')
cv_results_table = dynamodb.Table(os.environ['CV_ANALYSIS_RESULTS_TABLE'])
job_postings_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

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

    # Get user_id from Cognito claims
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized"})
        }

    # Extract job_id from query string
    job_id = event.get("queryStringParameters", {}).get("job_id")
    if not job_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Missing job_id"})
        }

    # Verify that the job_id belongs to this user
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

    # Fetch CV analysis results from CVAnalysisResults table
    try:
        results = cv_results_table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": f"RESULT#JD#{job_id}"}
        )
        items = results.get("Items", [])

        # Format the results to include only the necessary fields
        formatted = [
            {
                "job_id": job_id,
                "score": item.get("score"),
                "reasons": item.get("reasons", []),
                "created_at": item.get("created_at")
            }
            for item in items
        ]

        # Return successful response with CORS headers and formatted data
        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps(formatted, default=decimal_default)
        }

    except Exception as e:
        # Return error response with CORS headers
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Error fetching results: {str(e)}"})
        }