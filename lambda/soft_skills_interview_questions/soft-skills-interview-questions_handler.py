import os
import json
import boto3
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-preview-04-17")

# AWS clients
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

# Environment variables
job_table = dynamodb.Table(os.environ.get("JOB_DESC_TABLE"))
cv_bucket = os.environ["CV_BUCKET"]
results_table = dynamodb.Table(os.environ.get("CV_ANALYSIS_TABLE"))

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

    print("📥 Event:", event)
    # Parse request body
    if "body" in event and event["body"]:
        body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
    else:
        body = event

    job_id = body["job_id"]
    cv_id = body["cv_id"]

    # Extract user_id from JWT claims
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "User not authenticated"})
        }

    if not job_id or not cv_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing job_id or cv_id"})
        }

    try:
        # Get job description and check authorization
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
        result_obj = s3.get_object(Bucket=cv_bucket, Key=result_key)
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

        Basándote en la siguiente descripción del puesto y el CV del candidato, genera entre 3 y 5 preguntas abiertas centradas únicamente en habilidades blandas (como comunicación, trabajo en equipo, resolución de conflictos, liderazgo, adaptabilidad, etc.).

        - No incluyas habilidades técnicas ni preguntas genéricas.
        - Enfócate solo en habilidades blandas relevantes para el rol.

        Devuelve **únicamente** un objeto JSON con la siguiente estructura:

        {{
          "ss_questions": [
            "Pregunta 1",
            "Pregunta 2",
            "Pregunta 3",
            ...,
          ]
        }}

        No agregues explicaciones, texto adicional ni formato fuera del JSON.

        ---

        📄 Descripción del puesto:
        {job_description}

        📑 CV del candidato:
        {cv_text}
        """

        # Call Gemini model
        print("🔍 Generating soft skill questions...")
        print("Prompt for Gemini:", prompt)
        # Generate content using the Gemini model
        response = model.generate_content(
            contents=[prompt],
            generation_config={"response_mime_type": "application/json", "temperature": 0}
        )
        result_json = response.text
        print("✅ Result obtained from Gemini:", result_json)
        parsed = json.loads(result_json)

        # Update result in DynamoDB
        results_table.update_item(
            Key={
                "pk": f"RESULT#JD#{job_id}",
                "sk": f"RECRUITER#{user_id}#CV#{cv_id}"
            },
            UpdateExpression="SET ss_questions = :q",
            ExpressionAttributeValues={
                ":q": parsed["ss_questions"]
            }
        )

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({"ss_questions": parsed["ss_questions"]})
        }

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }