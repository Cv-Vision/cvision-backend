import json
import os
import boto3

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
        return {"statusCode": 204, "headers": CORS_HEADERS}

    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")
    if not job_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing job_id"})}

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    # Verify ownership of the job posting
    try:
        job_key = {"pk": f"JD#{job_id}", "sk": f"USER#{user_id}"}
        print("🔍 Checking ownership with key:", job_key)
        response = job_postings_table.get_item(Key=job_key)
        if "Item" not in response:
            return {"statusCode": 403, "headers": CORS_HEADERS, "body": json.dumps({"message": "You do not own this job posting"})}
        print("✅ Ownership confirmed")
    except Exception as e:
        print("❌ Error checking job ownership:", str(e))
        return {"statusCode": 500, "headers": CORS_HEADERS, "body": json.dumps({"error": f"Ownership check failed: {str(e)}"})}

    try:
        body = json.loads(event.get("body") or "{}")
        cv_ids = body.get("cv_ids", [])
        if not cv_ids:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing cv_ids in request body"})}

        deleted = []
        for cv_id in cv_ids:
            print(f"🔄 Processing cv_id: {cv_id}")

            # Delete S3 object
            s3_key = f"results/JD#{job_id}/{user_id}#{cv_id}.json"
            s3_key_upload = f"uploads/JD#{job_id}/{user_id}#{cv_id}.json"
            try:
                print(f"🧹 Deleting from S3: {s3_key}")
                s3.delete_object(Bucket=results_bucket, Key=s3_key)
            except Exception as e:
                print(f"⚠️ Could not delete S3 object: {e}")

            # Delete analysis result
            result_key = {"pk": f"RESULT#JD#{job_id}", "sk": f"RECRUITER#{user_id}#CV#{cv_id}"}
            try:
                print("🧹 Deleting from CV_ANALYSIS_RESULTS_TABLE:", result_key)
                results_table.delete_item(Key=result_key)
            except Exception as e:
                print(f"⚠️ Could not delete result from DynamoDB: {e}")

            # First get the JobApplication to extract the original CV key
            app_key = {"pk": f"JD#{job_id}", "sk": f"CV#{cv_id}"}
            try:
                app_item = job_applications_table.get_item(Key=app_key).get("Item")
                if app_item:
                    cv_upload_key = app_item.get("cv_upload_key")
                    if cv_upload_key:
                        print(f"🧹 Deleting uploaded CV from S3: {cv_upload_key}")
                        try:
                            s3.delete_object(Bucket=os.environ["CV_BUCKET"], Key=cv_upload_key)
                        except Exception as e:
                            print(f"⚠️ Failed to delete original CV file: {e}")
                else:
                    print(f"⚠️ No JobApplication found for {app_key}")
            except Exception as e:
                print(f"⚠️ Error getting JobApplication to delete original CV: {e}")

            # Now delete the JobApplication item
            try:
                print("🧹 Deleting from JobApplications:", app_key)
                job_applications_table.delete_item(Key=app_key)
            except Exception as e:
                print(f"⚠️ Could not delete JobApplication: {e}")

            deleted.append(cv_id)

        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"message": "Applications deleted successfully", "cv_ids": deleted})
        }

    except Exception as e:
        print("❌ General error:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
