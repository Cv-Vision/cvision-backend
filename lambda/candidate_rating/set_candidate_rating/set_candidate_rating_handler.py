import json
import os
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["JOB_APPLICATIONS_TABLE"])

# CORS headers
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    # Handle preflight CORS request
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": CORS_HEADERS
        }

    # Validate auth
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Usuario no autenticado"})
        }

    try:
        body = json.loads(event.get("body", "{}"))
        candidate_id = body.get("candidate_id")
        rating = body.get("rating")

        if not candidate_id or rating is None:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Faltan parámetros obligatorios"})
            }

        table.update_item(
            Key={"candidate_id": candidate_id},
            UpdateExpression="SET rating = :r",
            ExpressionAttributeValues={":r": rating}
        )

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({"message": "Rating actualizado correctamente"})
        }

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
