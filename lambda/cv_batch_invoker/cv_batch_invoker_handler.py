import json
import boto3
import os
import time
import random
from botocore.exceptions import ClientError
from db_handler import get_session
from models import JobPosting
from sqlalchemy.orm.exc import NoResultFound

sqs = boto3.client("sqs")
sqs_queue_url = os.environ.get("SQS_QUEUE_URL")

s3 = boto3.client("s3")

# Gemini API rate limits
MAX_REQUESTS_PER_MINUTE = 10
DELAY_SECONDS = 60
bucket = os.environ.get("BUCKET")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def send_message_with_retry(sqs_client, queue_url, message_body, delay_seconds=0, max_retries=3):
    """
    Send message to SQS with exponential backoff retry logic
    """
    for attempt in range(max_retries + 1):
        try:
            response = sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=message_body,
                DelaySeconds=min(delay_seconds, 900)  # SQS max delay is 15 minutes
            )
            return response

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['Throttling', 'ServiceUnavailable', 'RequestLimitExceeded']:
                if attempt < max_retries:
                    # Exponential backoff with jitter
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"⏳ SQS throttled, retrying in {wait_time:.2f}s (attempt {attempt + 1})")
                    time.sleep(wait_time)
                    continue
            print(f"❌ SQS Error: {error_code} - {e.response['Error']['Message']}")
            raise
        except Exception as e:
            print(f"❌ Unexpected error sending to SQS: {str(e)}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise

    raise Exception(f"Failed to send message to SQS after {max_retries + 1} attempts")


def calculate_processing_batches(total_files, batch_size=MAX_REQUESTS_PER_MINUTE):
    """
    Calculate how to batch files to respect rate limits
    """
    batches = []
    for i in range(0, total_files, batch_size):
        batch_number = i // batch_size
        delay_seconds = batch_number * DELAY_SECONDS  # 60 seconds between batches
        batch_files = list(range(i, min(i + batch_size, total_files)))
        batches.append({
            'batch_number': batch_number,
            'delay_seconds': delay_seconds,
            'file_indices': batch_files
        })
    return batches


def lambda_handler(event, context):
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
        print("🔍 Event:", event)
        body = event.get("body")
        if body and isinstance(body, str):
            body = json.loads(body)
        elif not body:
            body = {}
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Invalid JSON in request body"})
        }

    # Get job_id from the body
    job_id = body.get("job_id")

    if not job_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Falta job_id en el evento"})
        }

    # Get a database session from the connection layer
    session = get_session()

    try:
        # Verify job exists and belongs to user
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": f"El job_id {job_id} no existe o no pertenece al usuario"})
            }

    except Exception as e:
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al verificar job_id: {str(e)}"})
        }
    finally:
        session.close()

    # Get the list of CV files in the S3 bucket under the specified prefix (job_id)
    prefix = f"uploads/{job_id}/"

    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        contents = response.get("Contents", [])
        cv_files = [obj["Key"] for obj in contents if not obj["Key"].endswith("/")]

    except ClientError as e:
        print(f"❌ S3 Error: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Error accessing S3 bucket: {str(e)}"})
        }

    print(f"📁 Encontrados {len(cv_files)} archivos para procesar.")

    if len(cv_files) == 0:
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "No se encontraron archivos para procesar en el bucket"})
        }

    # Calculate processing batches to respect Gemini's rate limits
    batches = calculate_processing_batches(len(cv_files))
    total_batches = len(batches)
    estimated_completion_minutes = total_batches

    print(f"📊 Procesamiento programado en {total_batches} lotes de máximo {MAX_REQUESTS_PER_MINUTE} archivos")
    print(f"⏱️  Tiempo estimado de completado: ~{estimated_completion_minutes} minutos")

    # Send messages to SQS with calculated delays
    messages_sent = 0
    messages_failed = 0

    for batch in batches:
        batch_number = batch['batch_number']
        delay_seconds = batch['delay_seconds']

        print(f"📦 Procesando lote {batch_number + 1}/{total_batches} (delay: {delay_seconds}s)")

        for file_index in batch['file_indices']:
            cv_key = cv_files[file_index]

            payload = {
                "bucket": bucket,
                "cv_key": cv_key,
                "job_id": job_id,
                "user_id": user_id,
                "batch_number": batch_number,
                "file_index": file_index + 1,
                "total_files": len(cv_files)
            }

            try:
                # Send message to SQS with delay to respect rate limits
                response = send_message_with_retry(
                    sqs_client=sqs,
                    queue_url=sqs_queue_url,
                    message_body=json.dumps(payload),
                    delay_seconds=delay_seconds
                )

                print(f"✅ Mensaje enviado para: {cv_key} (MessageId: {response['MessageId'][:8]}...)")
                messages_sent += 1

            except Exception as e:
                print(f"❌ Error enviando mensaje para {cv_key}: {str(e)}")
                messages_failed += 1
                continue

    # Prepare response with processing summary
    processing_summary = {
        "total_files": len(cv_files),
        "messages_sent": messages_sent,
        "messages_failed": messages_failed,
        "total_batches": total_batches,
        "estimated_completion_minutes": estimated_completion_minutes,
        "rate_limit": f"{MAX_REQUESTS_PER_MINUTE} requests per minute"
    }

    if messages_failed > 0:
        status_code = 207  # Multi-status (partial success)
        message = f"Procesamiento iniciado con algunos errores: {messages_sent} enviados, {messages_failed} fallidos"
    else:
        status_code = 200
        message = f"Todos los {messages_sent} CVs enviados exitosamente para procesamiento"

    return {
        "statusCode": status_code,
        "headers": {
            **CORS_HEADERS,
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "message": message,
            "processing_summary": processing_summary
        })
    }