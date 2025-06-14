import os
import json
import base64
import uuid
import boto3
import fitz
import PIL.Image
from io import BytesIO
from datetime import datetime
import google.generativeai as genai

# Configurations and environment variables
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-preview-04-17")

s3 = boto3.client("s3")
dynamodb = boto3.resource('dynamodb')

job_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])
results_table = dynamodb.Table(os.environ["CV_ANALYSIS_RESULTS_TABLE"])

cv_bucket = os.environ["CV_BUCKET"]
results_bucket = os.environ["RESULTS_BUCKET"]


def extract_text_from_pdf_bytes(pdf_bytes):
    text = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text


def pdf_to_png_bytes(pdf_bytes):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        image = PIL.Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_file_to_bytes(image_bytes):
    with PIL.Image.open(BytesIO(image_bytes)) as img:
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


def lambda_handler(event, context):
    try:
        print("📥 Event:", event)
        # Parse request body
        if "body" in event and event["body"]:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        else:
            body = event

        cv_key = body["cv_key"]
        job_id = body["job_id"]
        user_id = body["user_id"]

        # Obtain CV from S3
        response = s3.get_object(Bucket=cv_bucket, Key=cv_key)
        cv_bytes = response["Body"].read()

        # Convert to PNG image
        ext = cv_key.lower().split('.')[-1]
        if ext == "pdf":
            image_bytes = pdf_to_png_bytes(cv_bytes)
        elif ext in ["png", "jpg", "jpeg"]:
            image_bytes = image_file_to_bytes(cv_bytes)
        else:
            return {"statusCode": 400, "body": json.dumps({"error": "Formato no soportado"})}

        # Get job description from DynamoDB
        result = job_table.get_item(Key={
            "pk": f"JD#{job_id}",
            "sk": f"USER#{user_id}"
        })
        item = result.get("Item")
        if not item:
            return {"statusCode": 404, "body": json.dumps({"error": "Job description no encontrada"})}

        job_description = item["description"]
        participant_id = str(uuid.uuid4())

        # Create prompt for Gemini
        prompt = f"""
    Actúa como un experto en recursos humanos especializado en evaluación de candidatos según su currículum.

    A continuación se presentarán varios currículums, cada uno en el siguiente formato:

    [participant_id] - [Texto del currículum]

    Tu tarea es evaluar cada uno de ellos según su adecuación a la descripción del puesto, considerando los requisitos de la descripción del puesto.
    No hay requisitos extra, mas que el candidato pertenezca a la industria correcta.
    Hay que seguir al pie de la letra lo que dice la descripción del puesto y en base a eso evaluar el currículum.

    Por cada currículum, devuelve una evaluación en formato JSON con esta estructura:

    {{
      "participant_id": "...",
      "score": [puntaje de 0 a 100],
      "reasons": [
        "razón 1",
        "razón 2",
        ...
      ]
    }}

    Importante: devuelve un objeto JSON por cada currículum, sin texto adicional.

    Descripción del puesto:
    {job_description}
    """

        # Call Gemini
        response = model.generate_content(
            contents=[
                prompt,
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(image_bytes).decode("utf-8")
                    }
                }
            ],
            generation_config={"response_mime_type": "application/json"},
        )

        result_json = response.text
        print("✅ Result obtained from Gemini:", result_json)

        # Parse result
        parsed = json.loads(result_json)
        if not all(k in parsed for k in ["participant_id", "score", "reasons"]):
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Formato de respuesta inesperado de Gemini"})
            }

        # Save to S3
        output_key = f"results/{job_id}/{participant_id}.json"
        s3.put_object(
            Bucket=results_bucket,
            Key=output_key,
            Body=result_json.encode("utf-8"),
            ContentType="application/json"
        )

        # Save to DynamoDB
        results_table.put_item(Item={
            "pk": f"JOB#{job_id}",
            "sk": f"PARTICIPANT#{participant_id}",
            "participant_id": participant_id,
            "user_id": user_id,
            "score": parsed["score"],
            "reasons": parsed.get("reasons", []),
            "s3_key": output_key,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Evaluación completada",
                "result_s3_path": f"s3://{results_bucket}/{output_key}",
                "participant_id": participant_id
            })
        }

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }