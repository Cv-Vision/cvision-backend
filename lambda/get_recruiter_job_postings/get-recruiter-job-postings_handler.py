import boto3
import json
import os
import decimal

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
    # Get user_id from the event
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized - user_id not found"})
        }

    # Build the query to get all job descriptions for the user
    try:
        response = table.query(
            IndexName='sk-index',
            KeyConditionExpression="sk = :sk", # Using the secondary index for sk
            ExpressionAttributeValues={
                ":sk": f"USER#{user_id}"
            }
        )
        items = response.get('Items', [])

        return {
            "statusCode": 200,
            "body": json.dumps(items, default=decimal_default),
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
