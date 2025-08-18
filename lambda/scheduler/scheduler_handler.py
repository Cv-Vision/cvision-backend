import json
import boto3
import os
from botocore.exceptions import ClientError

# --- Boto3 Clients ---
dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

# --- Configuration ---
BATCH_SIZE = 10  # Max number of messages to send per invocation

def lambda_handler(event, context):
    """
    This function is triggered by an EventBridge Schedule. It queries a GSI on the
    DynamoDB table to find tasks with a 'PENDING' status, sends them as messages
    to an SQS queue, and updates their status to 'QUEUED'.
    """
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    gsi_name = os.environ.get("GSI_NAME")
    sqs_queue_url = os.environ.get("SQS_QUEUE_URL")
    tasks_table = dynamodb.Table(table_name)

    # --- Query the GSI to find pending tasks efficiently ---
    try:
        response = tasks_table.query(
            IndexName=gsi_name,
            KeyConditionExpression="#s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "PENDING"},
            Limit=BATCH_SIZE
        )
        tasks_to_process = response.get("Items", [])

        if not tasks_to_process:
            print("No pending tasks found. Exiting.")
            return {"statusCode": 200, "body": "No pending tasks."}

    except ClientError as e:
        print(f"Error querying DynamoDB GSI: {e}")
        # Exit gracefully if we can't query the database
        return {"statusCode": 500, "body": "Failed to query tasks."}

    print(f"Found {len(tasks_to_process)} tasks to queue.")
    messages_sent = 0

    # --- Send messages to SQS and update DynamoDB status ---
    for task in tasks_to_process:
        job_id = task["job_id"]
        s3_key = task["s3_key"]

        try:
            # Step 1: Send the message to SQS
            sqs.send_message(
                QueueUrl=sqs_queue_url,
                MessageBody=json.dumps({
                    "job_id": job_id,
                    "s3_key": s3_key,
                })
            )

            # Step 2: Update the item's status to 'QUEUED'
            tasks_table.update_item(
                Key={"job_id": job_id, "s3_key": s3_key},
                UpdateExpression="set #s = :s",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":s": "QUEUED"},
            )
            messages_sent += 1
            print(f"Successfully queued task for: {s3_key}")

        except ClientError as e:
            print(f"Failed to queue task for {s3_key}: {e}")
            # Continue to the next task if one fails
            continue

    return {
        "statusCode": 200,
        "body": f"Successfully queued {messages_sent} of {len(tasks_to_process)} found tasks."
    }