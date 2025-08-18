import json
import boto3
import os

s3 = boto3.client("s3")
bucket = os.environ["UPLOADS_BUCKET"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS}

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    try:
        print("🔍 Event:", event)
        body = json.loads(event.get("body") or "{}")
        filename = body.get("filename")
        if not filename:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing filename"})}

        s3_key = f"candidates/{user_id}/{filename}"

        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "ContentType": "application/pdf"  # o dinámico según extensión
            },
            ExpiresIn=3600
        )

        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"upload_url": url, "s3_key": s3_key})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
