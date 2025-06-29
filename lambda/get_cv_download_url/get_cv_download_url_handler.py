import os
import json
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

JOB_POSTINGS_TABLE = os.environ["JOB_POSTINGS_TABLE"]
UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]

CORS_HEADERS = {
    "access-control-allow-origin": "http://localhost:3000",
    "access-control-allow-headers": "Content-Type,Authorization",
    "access-control-allow-methods": "OPTIONS,GET",
    "access-control-allow-credentials": "true"
}



def lambda_handler(event, context):
    # Preflight CORS
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "CORS OK"})
        }

    # Auth desde JWT
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Unauthorized"})
        }

    # Path params
    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")
    cv_id = path_params.get("cv_id")

    if not job_id or not cv_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing job_id or cv_id"})
        }

    try:
        table = dynamodb.Table(JOB_POSTINGS_TABLE)

        # Validar ownership del Job
        job_item = table.get_item(Key={"pk": f"JOB#{job_id}", "sk": f"JOB#{job_id}"}).get("Item")
        if not job_item or job_item.get("user_id") != user_id:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Forbidden - Not your job posting"})
            }

        # Buscar postulación y obtener el upload_key
        cv_item = table.get_item(Key={"pk": f"JD#{job_id}", "sk": f"CV#{cv_id}"}).get("Item")
        if not cv_item or "cv_upload_key" not in cv_item:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "CV not found"})
            }

        upload_key = cv_item["cv_upload_key"]
        filename = cv_item.get("original_filename", "CV.pdf")

        # Generar URL presignada (15 min)
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": UPLOADS_BUCKET, "Key": upload_key},
            ExpiresIn=900
        )

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "url": presigned_url,
                "filename": filename
            })
        }

    except ClientError as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
