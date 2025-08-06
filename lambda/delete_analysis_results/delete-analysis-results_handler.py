import json
import os
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime

# Initialize AWS resources
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

results_table = dynamodb.Table(os.environ["CV_ANALYSIS_RESULTS_TABLE"])
job_postings_table = dynamodb.Table(os.environ["JOB_POSTINGS_TABLE"])
job_applications_table = dynamodb.Table(os.environ["JOB_APPLICATIONS_TABLE"])
results_bucket = os.environ["RESULTS_BUCKET"]

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
        print("🟡 Preflight OPTIONS request")
        return {"statusCode": 204, "headers": CORS_HEADERS}

    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")
    print("🔎 job_id:", job_id)
    if not job_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing job_id"})}

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    print("🔐 user_id (from token):", user_id)
    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    # Verify ownership of the job posting
    try:
        job_key = {"pk": f"JD#{job_id}", "sk": f"USER#{user_id}"}
        print("🔍 Checking ownership with key:", job_key)
        response = job_postings_table.get_item(Key=job_key)
        if "Item" not in response:
            print("❌ Ownership check failed - job not found")
            return {"statusCode": 403, "headers": CORS_HEADERS, "body": json.dumps({"message": "You do not own this job posting"})}
        print("✅ Ownership confirmed")
    except Exception as e:
        print("❌ Exception in ownership check:", str(e))
        return {"statusCode": 500, "headers": CORS_HEADERS, "body": json.dumps({"error": f"Ownership check failed: {str(e)}"})}

    # Process the request to delete CV analysis results
    try:
        body = json.loads(event.get("body") or "{}")
        cv_ids = body.get("cv_ids", [])
        print("🧾 CV IDs to delete:", cv_ids)
        if not cv_ids:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing cv_ids in request body"})}

        deleted = []
        not_found = []
        print("🔄 Starting deletion process for CVs:", cv_ids)
        for cv_id in cv_ids:
            print(f"--- 🔄 Processing cv_id: {cv_id} ---")
            result_pk = f"RESULT#JD#{job_id}"
            result_sk = f"RECRUITER#{user_id}#CV#{cv_id}"
            s3_key = f"results/JD#{job_id}/{user_id}#{cv_id}.json"
            application_key = {"pk": f"JD#{job_id}", "sk": f"CV#{cv_id}"}

            print(f"🔑 Checking if result exists in DynamoDB: {result_pk}, {result_sk}")
            try:
                result_check = results_table.get_item(Key={"pk": result_pk, "sk": result_sk})
                if "Item" not in result_check:
                    print(f"⚠️ No se encontró análisis para cv_id {cv_id}, se omite")
                    not_found.append(cv_id)
                    continue
                print("✅ Análisis encontrado")
            except Exception as e:
                print(f"❌ Error verificando existencia en DynamoDB: {str(e)}")

            print(f"🗑️ Deleting DynamoDB item from CV_ANALYSIS_RESULTS_TABLE: {result_pk}, {result_sk}")
            try:
                results_table.delete_item(Key={"pk": result_pk, "sk": result_sk})
            except Exception as e:
                print(f"❌ Failed to delete from CV_ANALYSIS_RESULTS_TABLE: {str(e)}")

            print(f"🧹 Deleting S3 object: {s3_key}")
            try:
                s3.delete_object(Bucket=results_bucket, Key=s3_key)
            except Exception as e:
                print(f"❌ Failed to delete from S3: {str(e)}")

            print(f"✂️ Removing cv_s3_key from JobApplications for {application_key}")
            try:
                job_applications_table.update_item(
                    Key=application_key,
                    UpdateExpression="REMOVE cv_s3_key, score"
                )
            except Exception as e:
                print(f"❌ Failed to update JobApplications: {str(e)}")

            deleted.append(cv_id)
            if not deleted:
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {"message": "No analysis results found for given cv_ids", "not_found": not_found})
                }

        print("✅ All done. Deleted CVs:", deleted)
        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"message": "Deleted analysis results", "cv_ids": deleted})
        }

    except Exception as e:
        print("❌ General exception:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Failed to delete results: {str(e)}"})
        }
