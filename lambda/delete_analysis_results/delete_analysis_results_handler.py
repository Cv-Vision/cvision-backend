import json
import os
import boto3
from datetime import datetime

# Import ORM session handler and models
from db_handler import get_session
from models import JobPosting, CVAnalysisResult, JobApplication

s3 = boto3.client("s3")
bucket = os.environ["BUCKET"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
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

    # Get database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        # Verify ownership of the job posting
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            print("❌ Ownership check failed - job not found")
            return {"statusCode": 403, "headers": CORS_HEADERS,
                    "body": json.dumps({"message": "You do not own this job posting"})}
        print("✅ Ownership confirmed")

        # Process the request to delete CV analysis results
        body = json.loads(event.get("body") or "{}")
        cv_ids = body.get("cv_ids", [])
        print("🧾 CV IDs to delete:", cv_ids)
        if not cv_ids:
            return {"statusCode": 400, "headers": CORS_HEADERS,
                    "body": json.dumps({"message": "Missing cv_ids in request body"})}

        deleted = []
        not_found = []
        print("🔄 Starting deletion process for CVs:", cv_ids)
        for cv_id in cv_ids:
            print(f"--- 🔄 Processing cv_id: {cv_id} ---")

            # Find the analysis result
            analysis_result = session.query(CVAnalysisResult).filter(
                CVAnalysisResult.cv_hash == cv_id,
                CVAnalysisResult.job_posting_id == job_id
            ).first()

            if not analysis_result:
                print(f"⚠️ No se encontró análisis para cv_id {cv_id}, se omite")
                not_found.append(cv_id)
                continue

            print("✅ Analysis result found. Deleting from DB and S3.")

            # Delete S3 object
            try:
                s3.delete_object(Bucket=bucket, Key=analysis_result.s3_key)
                print("🧹 S3 object deleted")
            except Exception as e:
                print(f"❌ Failed to delete from S3: {str(e)}")

            # Delete the analysis result from the DB
            session.delete(analysis_result)

            # Update the JobApplication to remove the score
            job_application = session.query(JobApplication).filter(
                JobApplication.cv_hash == cv_id,
                JobApplication.job_posting_id == job_id
            ).first()

            if job_application:
                # Set score to null and remove the key
                job_application.score = None
                job_application.cv_s3_key = None
                print("✂️ JobApplication score and key removed")

            deleted.append(cv_id)

        # Commit all changes in a single transaction
        session.commit()
        print("✅ DB changes committed successfully")

        if not deleted:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "No analysis results found for given cv_ids", "not_found": not_found})
            }

        print("✅ All done. Deleted CVs:", deleted)
        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"message": "Deleted analysis results", "cv_ids": deleted})
        }

    except Exception as e:
        print("❌ General exception:", str(e))
        # Rollback changes in case of an error
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Failed to delete results: {str(e)}"})
        }
    finally:
        # Close the database session
        session.close()