import os
import json
import boto3
from boto3.dynamodb.conditions import Key
import decimal

dynamodb = boto3.resource("dynamodb")
job_applications_table = dynamodb.Table(os.environ["JOB_APPLICATIONS_TABLE"])

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
    # Handle CORS preflight request
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": CORS_HEADERS
        }
    # Get user_id from the event
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Usuario no autenticado"})
        }

    try:
        print("🔍 Event:", event)

        # ✅ Extract job_id from the path parameters
        job_id = event.get("pathParameters", {}).get("job_id")
        if not job_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Falta job_id"})
            }

        pk = f"JD#{job_id}"

        # Query by partition key (pk) -> job_id
        response = job_applications_table.query(
            KeyConditionExpression=Key("pk").eq(pk)
        )

        candidates = []
        for item in response.get("Items", []):
            candidates.append({
                "cv_id": item["sk"].replace("CV#", ""),
                "name": item.get("name"),
                "cv_s3_key": item.get("cv_s3_key"),
                "created_at": item.get("created_at"),
                "score": item.get("score"),
                "valoracion": item.get("valoracion")
            })

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps(
                {"job_id": job_id, "candidates": candidates},
                default=decimal_default)
        }

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
