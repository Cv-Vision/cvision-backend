import json
import boto3
import os

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
        file_name = event['Records'][0]['s3']['object']['key']

        # Get the file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=file_name)
        file_content = response['Body'].read()

        # Use Textract to extract text from the file
        textract_response = textract_client.detect_document_text(
            Document={'Bytes': file_content}
        )

        # Extract text from Textract response
        extracted_text = ''
        for item in textract_response['Blocks']:
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + '\n'

        # Call the Lambda function cv_processor with the extracted text
        payload = {
            'text': extracted_text
        }

        # Invoke the cv_processor Lambda function
        lambda_client.invoke(
            FunctionName=CV_PROCESSOR_LAMBDA_ARN,
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps(payload)
        )

        return {
            'statusCode': 200,
            'body': json.dumps('Textract and Lambda invocation succeeded')
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({"error": str(e)})
        }
