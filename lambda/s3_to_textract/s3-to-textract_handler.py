import json
import boto3
import os
import mimetypes
import time
import urllib.parse

# S3 client and Textract
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')
lambda_client = boto3.client('lambda')

# Lambda cv_processor
CV_PROCESSOR_LAMBDA_ARN = os.environ['CV_PROCESSOR_LAMBDA_ARN']


def lambda_handler(event, context):
    try:
        # Extracts bucket name and file name from the S3 event
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        raw_key = event['Records'][0]['s3']['object']['key']
        file_name = urllib.parse.unquote_plus(raw_key)
        print(f"Bucket: {bucket_name}, File: {file_name}")

        # Check the file type
        file_type, _ = mimetypes.guess_type(file_name)
        print(f"File type: {file_type}")

        if file_type not in ['application/pdf', 'image/jpeg', 'image/png']:
            raise Exception(f"Unsupported file type: {file_type}")

        print(f"Calling Textract to start text extraction for {file_name}...")

        # Start document text detection (asynchronous)
        textract_response = textract_client.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': bucket_name, 'Name': file_name}}
        )

        # Extract JobId from response
        job_id = textract_response['JobId']
        print(f"Textract job started with JobId: {job_id}")

        # Poll for the job status
        while True:
            # Check the status of the Textract job
            status_response = textract_client.get_document_text_detection(JobId=job_id)
            status = status_response['JobStatus']
            print(f"Job status: {status}")

            if status == 'SUCCEEDED':
                print("Textract job succeeded")
                break
            elif status == 'FAILED':
                raise Exception(f"Textract job failed with error: {status_response.get('ErrorMessage', 'Unknown error')}")
            else:
                # Wait for a few seconds before polling again
                time.sleep(5)

        # Extract text from Textract response
        extracted_text = ''
        for item in status_response['Blocks']:
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + '\n'
        print("Text extracted from document")

        # Call the Lambda function cv_processor with the extracted text
        payload = {
            'text': extracted_text
        }
        print(f"Invoking cv-processor Lambda with payload: {payload}")

        # Invoke the cv_processor Lambda function
        lambda_client.invoke(
            FunctionName="cv-processor",
            InvocationType="RequestResponse", # Asynchronous response
            Payload=json.dumps(payload)
        )
        print("cv-processor Lambda invoked")

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
