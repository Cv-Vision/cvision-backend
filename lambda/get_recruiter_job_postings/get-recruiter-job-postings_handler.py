import boto3
import json
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

def lambda_handler(event, context):
    # Get user_id from the event
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
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
            "body": json.dumps(items),
            "headers": {
                "Content-Type": "application/json"
            }
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
