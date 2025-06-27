import os
import json
import boto3
import google.generativeai as genai

# AWS clients
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

# CORS headers configuration
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": CORS_HEADERS
        }

    # Environment variables
    JOB_DESC_TABLE = os.environ.get("JOB_DESC_TABLE")
    RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET")
    ANALYSIS_TABLE = os.environ.get("CV_ANALYSIS_TABLE")
    API_KEY = os.environ.get("GEMINI_API_KEY")

    if not all([JOB_DESC_TABLE, RESULTS_BUCKET, ANALYSIS_TABLE, API_KEY]):
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing environment variables"})
        }

    genai.configure(api_key=API_KEY)

    # Extract user_id from JWT claims
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "User not authenticated"})
        }

    # Parse input
    job_id = event.get("job_id")
    cv_id = event.get("cv_id")

    if not job_id or not cv_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing job_id or cv_id"})
        }

    try:
        # Get job description and check authorization
        job_table = dynamodb.Table(JOB_DESC_TABLE)
        job_response = job_table.get_item(Key={"job_id": job_id})
        if "Item" not in job_response:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Job not found"})
            }
        job_item = job_response["Item"]
        if job_item.get("user_id") != user_id:
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Unauthorized"})
            }
        job_description = job_item.get("description", "")

        # Get CV text from S3
        result_key = f"results/{cv_id}.json"
        result_obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=result_key)
        result_data = json.loads(result_obj["Body"].read().decode("utf-8"))
        cv_text = result_data.get("cv_text") or result_data.get("text")
        if not cv_text:
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "CV text not found in S3 object"})
            }

        # Prompt for Gemini
        prompt = f"""
Actúa como reclutador experto en entrevistas laborales.

Basándote en la siguiente descripción del puesto y el CV del candidato, genera entre 3 y 5 **preguntas abiertas centradas únicamente en habilidades blandas** (como comunicación, trabajo en equipo, resolución de conflictos, liderazgo, adaptabilidad, etc.).

No incluyas habilidades técnicas ni preguntas genéricas.

Entrega solo las preguntas en formato de lista clara y profesional.

---

📄 Descripción del puesto:
{job_description}

📑 CV del candidato:
{cv_text}
"""

        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        questions = [line.strip("-•0123456789. ").strip() for line in raw_text.split("\n") if line.strip()]
        questions = [q for q in questions if q]

        # Save to DynamoDB
        analysis_table = dynamodb.Table(ANALYSIS_TABLE)
        analysis_table.put_item(Item={
            "cv_id": cv_id,
            "job_id": job_id,
            "user_id": user_id,
            "soft_skill_questions": questions
        })

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({"soft_skill_questions": questions})
        }

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }