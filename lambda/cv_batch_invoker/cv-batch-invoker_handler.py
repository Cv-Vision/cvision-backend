import json
import time
import boto3
import os

lambda_client = boto3.client("lambda")

# Gemini Free Tier Limit
MAX_REQUESTS_PER_MINUTE = 10
DELAY_SECONDS = 60

CV_BUCKET = os.environ.get("CV_BUCKET")  # bucket donde están los CVs
CV_PREFIX = os.environ.get("CV_PREFIX", "uploads/")  # opcional prefijo


def lambda_handler(event, context):
    s3 = boto3.client("s3")

    # Obtener lista de archivos en el bucket
    response = s3.list_objects_v2(Bucket=CV_BUCKET, Prefix=CV_PREFIX)
    contents = response.get("Contents", [])
    cv_files = [obj["Key"] for obj in contents if not obj["Key"].endswith("/")]

    print(f"Encontrados {len(cv_files)} archivos para procesar.")

    # Obtener job_id del body del event (pasado desde frontend)
    job_id = event.get("job_id")
    if not job_id:
        return {"statusCode": 400, "body": "Falta job_id en el evento"}

    # Dividir en batches de 10
    for i in range(0, len(cv_files), MAX_REQUESTS_PER_MINUTE):
        batch = cv_files[i:i + MAX_REQUESTS_PER_MINUTE]
        print(f"Procesando batch {i // MAX_REQUESTS_PER_MINUTE + 1}: {batch}")

        for key in batch:
            payload = {
                "bucket": CV_BUCKET,
                "key": key,
                "job_id": job_id
            }

            # Invocar la función Lambda `cv_processor`
            lambda_client.invoke(
                FunctionName="cv_processor",
                InvocationType="Event",  # async
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
