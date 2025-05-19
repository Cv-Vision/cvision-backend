import json
import boto3
import os
import mimetypes
import time
import urllib.parse
import zipfile

# Initialize AWS clients
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')
lambda_client = boto3.client('lambda')

# Environment variable for downstream Lambda
CV_PROCESSOR_LAMBDA_ARN = os.environ['CV_PROCESSOR_LAMBDA_ARN']

def lambda_handler(event, context):
    try:
        # Extract bucket and object key from the event
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        raw_key = event['Records'][0]['s3']['object']['key']
        file_key = urllib.parse.unquote_plus(raw_key)
        print(f"Bucket: {bucket_name}, File: {file_key}")

        # Guess MIME type to determine how to handle the file
        file_type, _ = mimetypes.guess_type(file_key)
        print(f"File type: {file_type}")

        if file_key.lower().endswith('.zip'):
            print("Handling ZIP file...")
            handle_zip_file(bucket_name, file_key)
        elif file_type in ['application/pdf', 'image/jpeg', 'image/png']:
            print("Handling single supported file...")
            process_with_textract(bucket_name, file_key)
        else:
            raise Exception(f"Unsupported file type: {file_type}")

        return {
            'statusCode': 200,
            'body': json.dumps('Textract and Lambda invocation succeeded')
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({"error": str(e)})
        }

def process_with_textract(bucket_name, file_key):
    """
    Start Textract on a supported file and send the result to cv_processor Lambda.
    """
    print(f"Calling Textract to start text extraction for {file_key}...")

    # Start an asynchronous Textract job
    response = textract_client.start_document_text_detection(
        DocumentLocation={'S3Object': {'Bucket': bucket_name, 'Name': file_key}}
    )

    job_id = response['JobId']
    print(f"Textract job started with JobId: {job_id}")

    # Poll Textract job status until it's done
    while True:
        status_response = textract_client.get_document_text_detection(JobId=job_id)
        status = status_response['JobStatus']
        print(f"Job status: {status}")

        if status == 'SUCCEEDED':
            print("Textract job succeeded")
            break
        elif status == 'FAILED':
            raise Exception(f"Textract job failed: {status_response.get('ErrorMessage', 'Unknown error')}")
        else:
            time.sleep(5)

    # Collect extracted text from Textract response
    extracted_text = ''
    for item in status_response['Blocks']:
        if item['BlockType'] == 'LINE':
            extracted_text += item['Text'] + '\n'

    print("Text extracted from document")

    # Construct payload for cv_processor Lambda
    payload = {
        'text': extracted_text,
        'job_description': {
            'title': 'Senior Backend Developer',
            'description': 'Looking for an experienced backend developer with strong knowledge of Kotlin and distributed systems.',
            'location': 'Remote',
            'level': 'Senior',
            'skills': ['Kotlin', 'Spring Boot', 'PostgreSQL', 'Docker', 'CI/CD']
        }
    }

    print(f"Invoking cv_processor Lambda with payload: {payload}")

    # Invoke cv_processor Lambda with the result
    lambda_client.invoke(
        FunctionName=CV_PROCESSOR_LAMBDA_ARN,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload)
    )

def handle_zip_file(bucket_name, zip_key):
    """
    Handle ZIP files uploaded to S3: extract PDFs and process them with Textract.
    """
    # Download ZIP from S3 to /tmp
    local_zip_path = f"/tmp/{os.path.basename(zip_key)}"
    s3_client.download_file(bucket_name, zip_key, local_zip_path)
    print(f"Downloaded ZIP: {local_zip_path}")

    # Extract files to /tmp
    extracted_dir = "/tmp/unzipped"
    os.makedirs(extracted_dir, exist_ok=True)

    with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
        zip_ref.extractall(extracted_dir)
    print(f"Extracted files to: {extracted_dir}")

    # Loop through extracted files
    for filename in os.listdir(extracted_dir):
        file_path = os.path.join(extracted_dir, filename)
        mime_type, _ = mimetypes.guess_type(file_path)

        if mime_type == "application/pdf":
            temp_key = f"temp_extracted/{filename}"

            # Upload PDF to a temporary S3 location
            s3_client.upload_file(file_path, bucket_name, temp_key)
            print(f"Uploaded extracted PDF to S3: {temp_key}")

            # Process it with Textract
            process_with_textract(bucket_name, temp_key)

            # Clean up S3 temp file after processing
            s3_client.delete_object(Bucket=bucket_name, Key=temp_key)
            print(f"Deleted temporary S3 file: {temp_key}")
        else:
            print(f"Skipped unsupported file in ZIP: {filename}")
