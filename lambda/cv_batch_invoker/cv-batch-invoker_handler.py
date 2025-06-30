import json
import time
import boto3
import os

lambda_client = boto3.client("lambda")
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client("s3")

MAX_REQUESTS_PER_MINUTE = 10
DELAY_SECONDS = 60
FINAL_WAIT_SECONDS = 2  # Nueva espera final para evitar pérdida del último invoke

cv_bucket = os.environ.get("CV_BUCKET")
job_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")

    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    try:
        body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        job_id = body.get("job_id")
        if not job_id:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing job_id"})}
    except Exception:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Invalid body"})}

    job_pk = f"JD#{job_id.replace('JD#', '')}"
    job_sk = f"USER#{user_id}"
    try:
        job = job_table.get_item(Key={"pk": job_pk, "sk": job_sk})
        if "Item" not in job:
            return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"message": "Job not found"})}
    except Exception as e:
        return {"statusCode": 500, "headers": CORS_HEADERS, "body": json.dumps({"message": str(e)})}

    prefix = f"uploads/{job_pk}/"
    response = s3.list_objects_v2(Bucket=cv_bucket, Prefix=prefix)
    contents = response.get("Contents", [])
    cv_keys = [obj["Key"] for obj in contents if not obj["Key"].endswith("/")]

    # Batch en grupos de 10
    total_batches = (len(cv_keys) + MAX_REQUESTS_PER_MINUTE - 1) // MAX_REQUESTS_PER_MINUTE

    for batch_index, i in enumerate(range(0, len(cv_keys), MAX_REQUESTS_PER_MINUTE)):
        batch = cv_keys[i:i + MAX_REQUESTS_PER_MINUTE]

        for cv_key in batch:
            try:
                payload = {
                    "cv_key": cv_key,
                    "job_id": job_pk,
                    "user_id": user_id
                }
                lambda_client.invoke(
                    FunctionName=os.environ["CV_PROCESSOR_FUNCTION_NAME"],
                    InvocationType="Event",  # async
                    Payload=json.dumps(payload)
                )
                print(f"✅ Lanzado procesamiento para {cv_key}")
            except Exception as e:
                print(f"❌ Fallo al invocar Lambda para {cv_key}: {e}")

        if batch_index + 1 < total_batches:
            print("⏳ Esperando 60s antes del siguiente batch...")
            time.sleep(DELAY_SECONDS)
        else:
            print("✅ Último batch procesado. Esperando 2s antes de finalizar para asegurar envío...")
            time.sleep(FINAL_WAIT_SECONDS)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"message": f"{len(cv_keys)} CVs lanzados para análisis en lotes."})
    }
