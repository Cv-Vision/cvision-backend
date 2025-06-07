import json
import time
import boto3
import os

lambda_client = boto3.client("lambda")

MAX_REQUESTS_PER_MINUTE = 10
DELAY_SECONDS = 60

CV_BUCKET = os.environ.get("CV_BUCKET")
CV_PREFIX = os.environ.get("CV_PREFIX", "uploads/")


def lambda_handler(event, context):
    s3 = boto3.client("s3")

    # Obtener lista de archivos en el bucket
    response = s3.list_objects_v2(Bucket=CV_BUCKET, Prefix=CV_PREFIX)
    contents = response.get("Contents", [])
    cv_files = [obj["Key"] for obj in contents if not obj["Key"].endswith("/")]

    print(f"Encontrados {len(cv_files)} archivos para procesar.")

    # Parsear el body si viene como string
    try:
        body = event.get("body")
        if body and isinstance(body, str):
            body = json.loads(body)
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Invalid JSON in request body"})
        }

    # Obtener job_id desde body
    job_id = None
    if body:
        job_id = body.get("job_id")

    if not job_id:
        return {"statusCode": 400, "body": json.dumps({"message": "Falta job_id en el evento"})}

    # Get user_id from the event
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Unauthorized - user_id not found"})
        }

    if len(cv_files) == 0:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "No se encontraron archivos para procesar en el bucket"})
        }

    # Procesar en batches
    for i in range(0, len(cv_files), MAX_REQUESTS_PER_MINUTE):
        batch = cv_files[i:i + MAX_REQUESTS_PER_MINUTE]
        print(f"Procesando batch {i // MAX_REQUESTS_PER_MINUTE + 1}: {batch}")

        for key in batch:
            payload = {
                "bucket": CV_BUCKET,
                "cv_key": key,
                "job_id": job_id,
                "user_id": user_id
            }

            lambda_client.invoke(
                FunctionName="cv-processor",
                InvocationType="Event",
                Payload=json.dumps(payload)
            )
            print(f"✅ Invocado cv_processor para: {key}")

        if i + MAX_REQUESTS_PER_MINUTE < len(cv_files):
            print(f"⏳ Esperando {DELAY_SECONDS} segundos para el próximo batch...")
            time.sleep(DELAY_SECONDS)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Todos los CVs enviados a procesamiento"})
    }
