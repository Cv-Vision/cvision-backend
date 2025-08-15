python
import os
import json
import base64
from io import BytesIO
import fitz
import PIL.Image
import boto3
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-2.5-flash")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
cv_bucket = os.getenv("CV_BUCKET")
results_bucket = os.getenv("RESULTS_BUCKET")
results_table = dynamodb.Table(os.getenv("RESULTS_TABLE"))
job_table = dynamodb.Table(os.getenv("JOBS_TABLE"))

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

def calculate_sha256(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()

def lambda_handler(event, context):
    try:
        if "body" in event and event["body"]:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        else:
            body = event

        cv_key = body["cv_key"]
        job_id = body["job_id"]
        user_id = body["user_id"]

        # Descargar CV desde S3
        response = s3.get_object(Bucket=cv_bucket, Key=cv_key)
        cv_bytes = response["Body"].read()

        cv_id = calculate_sha256(cv_bytes)

        # Convertir a imagen
        ext = cv_key.lower().split('.')[-1]
        if ext == "pdf":
            image_bytes = pdf_to_png_bytes(cv_bytes)
        elif ext in ["png", "jpg", "jpeg"]:
            image_bytes = image_file_to_bytes(cv_bytes)
        else:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Formato no soportado"})
            }

        # Obtener descripción del puesto desde DynamoDB
        result = job_table.get_item(Key={
            "pk": job_id if job_id.startswith("JD#") else f"JD#{job_id}",
            "sk": f"USER#{user_id}"
        })
        item = result.get("Item")
        if not item:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Job description no encontrada"})
            }

        job_description = item["description"]
        experience_level = item.get("experience_level")
        english_level = item.get("english_level")
        industry_experience = item.get("industry_experience")
        contract_type = item.get("contract_type")
        additional_requirements = item.get("additional_requirements")

        additional_requirements_text = ""
        if experience_level:
            additional_requirements_text += f"\nNivel de experiencia requerido: {experience_level}"
        if english_level:
            additional_requirements_text += f"\nNivel de inglés requerido: {english_level}"
        if industry_experience:
            if industry_experience.get("required", False):
                industry = industry_experience.get("industry", "")
                additional_requirements_text += f"\nExperiencia en la industria requerida: {industry}"
            else:
                additional_requirements_text += "\nNo se requiere experiencia específica en la industria."
        if contract_type:
            additional_requirements_text += f"\nTipo de contrato: {contract_type}"
        if additional_requirements:
            additional_requirements_text += f"\nRequisitos adicionales: {additional_requirements}"

        prompt = f"""
        Actúa como un experto en recursos humanos especializado en evaluación de candidatos según su currículum.

        A continuación se presentarán varios currículums.

        Tu tarea es evaluar cada uno de ellos según su adecuación a la descripción del puesto, considerando los requisitos de la descripción del puesto y los requisitos adicionales especificados.
        Hay que seguir al pie de la letra lo que dice la descripción del puesto y los requisitos adicionales, y en base a eso evaluar el currículum.
        También debes identificar posibles habilidades blandas que el candidato pueda tener, solo si están explícita o claramente inferidas a partir de su experiencia o logros.
        Por cada currículum, devuelve una evaluación en formato JSON con esta estructura:

        {{
          "name" : ("nombre del candidato"),
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

        Requisitos adicionales:{additional_requirements_text}
        """

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
            generation_config={"response_mime_type": "application/json", "temperature": 0},
        )

        result_json = response.text
        parsed = json.loads(result_json)
        if isinstance(parsed, list):
            parsed = parsed[0]
        parsed["name"] = parsed["name"].title()

        output_key = f"results/{job_id}/{user_id}#{cv_id}.json"
        s3.put_object(
            Bucket=results_bucket,
            Key=output_key,
            Body=result_json.encode("utf-8"),
            ContentType="application/json"
        )

        results_table.put_item(Item={
            "pk": f"RESULT#{job_id}",
            "sk": f"CANDIDATE#{user_id}#CV#{cv_id}",
            "job_id": job_id,
            "name": parsed["name"],
            "candidate_id": user_id,
            "score": parsed["score"],
            "reasons": parsed.get("reasons", []),
            "s3_key": output_key,
            "created_at": datetime.utcnow().isoformat()
        })

        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Evaluación completada",
                "result_s3_path": f"s3://{results_bucket}/{output_key}",
                "candidate_id": user_id,
                "result": parsed
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }