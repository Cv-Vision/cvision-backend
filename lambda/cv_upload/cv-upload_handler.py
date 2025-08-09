import json
import os
import boto3
import base64
from datetime import datetime

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

candidates_table = dynamodb.Table(os.environ["CANDIDATES_TABLE"])
uploads_bucket = os.environ["UPLOADS_BUCKET"]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    print("📥 Event received:", json.dumps(event))

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS}

    # Obtener usuario autenticado
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    try:
        body = json.loads(event.get("body") or "{}")
        file_content_base64 = body.get("file_content")
        file_name = body.get("file_name")

        if not file_content_base64 or not file_name:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Missing file_content or file_name"})
            }

        # Guardar el archivo en S3
        s3_key = f"cvs/{user_id}/{file_name}"
        file_bytes = base64.b64decode(file_content_base64)

        s3.put_object(
            Bucket=uploads_bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf"
        )
        print(f"✅ CV guardado en S3: {s3_key}")

        # Actualizar DynamoDB con la referencia al CV
        candidates_table.update_item(
            Key={"pk": f"USER#{user_id}"},
            UpdateExpression="SET cv_upload_key = :cv_key, cv_updated_at = :updated_at",
            ExpressionAttributeValues={
                ":cv_key": s3_key,
                ":updated_at": datetime.utcnow().isoformat()
            }
        )
        print(f"✅ Registro actualizado en DynamoDB para {user_id}")

        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({
                "message": "CV uploaded successfully",
                "cv_key": s3_key
            })
        }

    except Exception as e:
        print("❌ Error al guardar el CV:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
