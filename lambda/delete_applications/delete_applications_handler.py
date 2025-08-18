import json
import os
import boto3
from datetime import datetime
from sqlalchemy import and_

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
    if not job_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"message": "Missing job_id"})}

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"message": "Unauthorized"})}

    # New: Get database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        # New: Verify ownership of the job posting
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            print("❌ Ownership check failed - job not found")
            return {"statusCode": 403, "headers": CORS_HEADERS,
                    "body": json.dumps({"message": "You do not own this job posting"})}
        print("✅ Ownership confirmed")

        body = json.loads(event.get("body") or "{}")
        cv_ids = body.get("cv_ids", [])
        if not cv_ids:
            return {"statusCode": 400, "headers": CORS_HEADERS,
                    "body": json.dumps({"message": "Missing cv_ids in request body"})}

        deleted = []
        for cv_hash in cv_ids:
            print(f"🔄 Processing cv_id: {cv_hash}")

            # New: Find the JobApplication and the related CV analysis result
            job_application = session.query(JobApplication).filter(
                and_(
                    JobApplication.cv_hash == cv_hash,
                    JobApplication.job_posting_id == job_id
                )
            ).first()

            if not job_application:
                print(f"⚠️ No se encontró JobApplication para {cv_hash}, se omite")
                continue

            # Get the S3 keys before deleting the DB entries
            original_cv_key = job_application.cv_upload_key
            analysis_result_key = None
            if job_application.analysis_result:
                analysis_result_key = job_application.analysis_result.s3_key

            # Delete S3 objects
            if original_cv_key:
                try:
                    print(f"🧹 Deleting original CV from S3: {original_cv_key}")
                    s3.delete_object(Bucket=bucket, Key=original_cv_key)
                except Exception as e:
                    print(f"⚠️ Failed to delete original CV file: {e}")

            if analysis_result_key:
                try:
                    print(f"🧹 Deleting analysis result from S3: {analysis_result_key}")
                    s3.delete_object(Bucket=bucket, Key=analysis_result_key)
                except Exception as e:
                    print(f"⚠️ Failed to delete analysis result file: {e}")

            # Delete the JobApplication. The CVAnalysisResult will be deleted via cascade
            session.delete(job_application)
            deleted.append(cv_hash)

        # Commit all changes in a single transaction
        session.commit()
        print("✅ DB changes committed successfully")

        if not deleted:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "No applications found for given cv_ids"})
            }

        print("✅ All done. Deleted CVs:", deleted)
        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"message": "Applications deleted successfully", "cv_ids": deleted})
        }

    except Exception as e:
        print("❌ General exception:", str(e))
        # Rollback changes in case of an error
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Failed to delete applications: {str(e)}"})
        }
    finally:
        # Close the database session
        session.close()