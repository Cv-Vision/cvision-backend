import os
import json
import base64
import boto3
import fitz
import PIL.Image
from io import BytesIO
from datetime import datetime
import google.generativeai as genai
import hashlib

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-preview-04-17")

s3 = boto3.client("s3")
dynamodb = boto3.resource('dynamodb')

job_table = dynamodb.Table(os.environ['JOB_POSTINGS_TABLE'])
results_table = dynamodb.Table(os.environ["CV_ANALYSIS_RESULTS_TABLE"])
job_applications_table = dynamodb.Table(os.environ["JOB_APPLICATIONS_TABLE"])

cv_bucket = os.environ["CV_BUCKET"]
results_bucket = os.environ["RESULTS_BUCKET"]

def save_job_application(job_id, cv_id, name, cv_s3_key):
    pk = f"JOB#{job_id}"
    sk = f"CV#{cv_id}"

    # Check if the application already exists
    existing = job_applications_table.get_item(Key={"pk": pk, "sk": sk})
    if "Item" not in existing:
        item = {
            "pk": pk,
            "sk": sk,
            "name": name,
            "cv_s3_key": cv_s3_key,
            "created_at": datetime.utcnow().isoformat()
        }
        job_applications_table.put_item(Item=item)
        print(f"Aplicación guardada: job {job_id} - cv {cv_id}")
    else:
        print(f"Aplicación ya existe: job {job_id} - cv {cv_id}")

# Function to calculate SHA-256 hash of file bytes -> this is to generate a unique identifier for the CV
def calculate_sha256(file_bytes):
    sha256_hash = hashlib.sha256()
    sha256_hash.update(file_bytes)
    return sha256_hash.hexdigest()

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

        # Calculate cv_id SHA256 based on file bytes (unique identifier)
        cv_id = calculate_sha256(cv_bytes)

        # Check if result already exists
        existing = results_table.get_item(Key={
            "pk": f"RESULT#{job_id}#CV#{cv_id}",
            "sk": f"RECRUITER#{user_id}#CV#{cv_id}"
        })
        if "Item" in existing:
            print("📦 Resultado ya existe. Se omite análisis.")
            output_key = f"results/{job_id}/{user_id}#{cv_id}.json"
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Análisis ya existía. No se volvió a procesar.",
                    "result_s3_path": f"s3://{results_bucket}/{output_key}",
                    "recruiter_id": user_id
                })
            }

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
            "pk": job_id if job_id.startswith("JD#") else f"JD#{job_id}",
            "sk": f"USER#{user_id}"
        })
        item = result.get("Item")
        if not item:
            return {"statusCode": 404, "body": json.dumps({"error": "Job description no encontrada"})}

        job_description = item["description"]


        # Create prompt for Gemini
        prompt = f"""
    Actúa como un experto en recursos humanos especializado en evaluación de candidatos según su currículum.

    A continuación se presentarán varios currículums.

    Tu tarea es evaluar cada uno de ellos según su adecuación a la descripción del puesto, considerando los requisitos de la descripción del puesto.
    No hay requisitos extra, mas que el candidato pertenezca a la industria correcta.
    Hay que seguir al pie de la letra lo que dice la descripción del puesto y en base a eso evaluar el currículum.
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
            generation_config={"response_mime_type": "application/json",
                               "temperature": 0
                               },
        )

        result_json = response.text
        print("✅ Result obtained from Gemini:", result_json)

        parsed = json.loads(result_json)

        # Save result to S3
        output_key = f"results/{job_id}/{user_id}#{cv_id}.json"
        s3.put_object(
            Bucket=results_bucket,
            Key=output_key,
            Body=result_json.encode("utf-8"),
            ContentType="application/json"
        )

        # Save result to DynamoDB
        results_table.put_item(Item={
            "pk": f"RESULT#{job_id}#CV#{cv_id}",
            "sk": f"RECRUITER#{user_id}#CV#{cv_id}",
            "job_id": job_id,
            "name": parsed["name"],
            "recruiter_id": user_id,
            "score": parsed["score"],
            "reasons": parsed.get("reasons", []),
            "s3_key": output_key,
            "created_at": datetime.utcnow().isoformat()
        })

        # Save job application to DynamoDB
        save_job_application(job_id, cv_id, parsed.get("name"), cv_key)

        # Update job posting to add cv_id
        job_posting = job_table.get_item(Key={
            "pk": job_id if job_id.startswith("JD#") else f"JD#{job_id}",
            "sk": f"USER#{user_id}"
        }).get("Item")

        if job_posting:
            candidates = job_posting.get("candidates", [])
            if cv_id not in candidates:
                candidates.append(cv_id)
                job_table.update_item(
                    Key={"pk": job_posting["pk"], "sk": job_posting["sk"]},
                    UpdateExpression="SET candidates = :candidates",
                    ExpressionAttributeValues={":candidates": candidates}
                )
                print(f"Aplicación {cv_id} agregado a JobPosting {job_id}")
            else:
                print(f"Aplicación {cv_id} ya estaba en JobPosting {job_id}")
        else:
            print(f"JobPosting {job_id} no encontrado para actualizar aplicaciones.")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Evaluación completada",
                "result_s3_path": f"s3://{results_bucket}/{output_key}",
                "recruiter_id": user_id
            })
        }

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
