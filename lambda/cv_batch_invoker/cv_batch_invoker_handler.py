import json
import time
import boto3
import os

lambda_client = boto3.client("lambda")

MAX_REQUESTS_PER_MINUTE = 10
DELAY_SECONDS = 60

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client("s3")

cv_bucket = os.environ.get("CV_BUCKET")
job_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

# CORS headers configuration
# Note: In production, replace the Origin with our actual domain
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"  # 24 hours
}

def lambda_handler(event, context):
    # Handle preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            "statusCode": 204,  # No content for OPTIONS
            "headers": CORS_HEADERS,
            "body": ""
        }

    # Get user_id from the event
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Unauthorized - user_id not found"})
        }

    # Parse the request body
    try:
        body = event.get("body")
        if body and isinstance(body, str):
            body = json.loads(body)
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Invalid JSON in request body"})
        }

    # Get job_id from the body
    job_id = body.get("job_id")

    if not job_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Falta job_id en el evento"})}

    # Verify if job_id exists in the DynamoDB table
    raw_job_id = job_id.replace("JD#", "") if job_id.startswith("JD#") else job_id
    job_pk = f"JD#{raw_job_id}"
    job_sk = f"USER#{user_id}"
    try:
        job_result = job_table.get_item(Key={"pk": job_pk, "sk": job_sk})
        if "Item" not in job_result:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": f"El job_id {job_id} no existe o no pertenece al usuario"})
            }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al verificar job_id: {str(e)}"})
        }

    # Get the list of CV files in the S3 bucket under the specified prefix (job_id)
    prefix = f"uploads/{job_id}/"

    response = s3.list_objects_v2(Bucket=cv_bucket, Prefix=prefix)
    contents = response.get("Contents", [])
    cv_files = [obj["Key"] for obj in contents if not obj["Key"].endswith("/")]

    print(f"Encontrados {len(cv_files)} archivos para procesar.")


    if len(cv_files) == 0:
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "No se encontraron archivos para procesar en el bucket"})
        }

    # Process the CV files in batches
    for i in range(0, len(cv_files), MAX_REQUESTS_PER_MINUTE):
        batch = cv_files[i:i + MAX_REQUESTS_PER_MINUTE]
        print(f"Procesando batch {i // MAX_REQUESTS_PER_MINUTE + 1}: {batch}")

        for key in batch:
            payload = {
                "bucket": cv_bucket,
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
        "headers": {
            **CORS_HEADERS,
            "Content-Type": "application/json"
        },
        "body": json.dumps({"message": "Todos los CVs enviados a procesamiento"})
    }
