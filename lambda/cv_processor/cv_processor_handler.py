import os
import json
import base64
import boto3
import fitz
import PIL.Image
from io import BytesIO
import google.generativeai as genai
import hashlib

# Import ORM session handler and models
from db_handler import get_session
from models import JobPosting, JobApplication, CVAnalysisResult

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-2.5-flash")

s3 = boto3.client("s3")

bucket = os.environ["BUCKET"]

def save_or_update_job_application(session, job_id, user_id, name, score, upload_key, cv_hash):
    """
    Saves or updates a JobApplication entry using the ORM.
    """
    try:
        # Check if an application already exists based on the CV hash
        existing_application = session.query(JobApplication).filter(
            JobApplication.cv_hash == cv_hash
        ).first()

        if existing_application:
            print(f"🔄 Existing JobApplication found for hash {cv_hash}. Updating...")
            existing_application.name = name
            existing_application.cv_upload_key = upload_key
            existing_application.score = score
            session.add(existing_application)
            return existing_application
        else:
            print(f"💾 Saving new JobApplication for job_id: {job_id}")
            new_application = JobApplication(
                job_posting_id=job_id,
                user_id=user_id,
                cv_upload_key=upload_key,
                cv_hash=cv_hash,
                score=score,
                name=name
            )
            session.add(new_application)
            return new_application
    except Exception as e:
        print("❌ Error saving/updating JobApplication:", str(e))
        raise # Re-raise the exception to trigger rollback

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
    # Get a database session from the connection layer
    session = get_session()

    try:
        print("🔍 Event:", event)
        # Parse request body
        if "body" in event and event["body"]:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        else:
            body = event

        cv_key = body["cv_key"]
        job_id = body["job_id"]
        user_id = body["user_id"]

        # Get CV from S3
        response = s3.get_object(Bucket=bucket, Key=cv_key)
        cv_bytes = response["Body"].read()

        # Calculate cv_id SHA256 based on file bytes (unique identifier)
        cv_id = calculate_sha256(cv_bytes)

        # Check for existing result using ORM query
        existing_result = session.query(CVAnalysisResult).filter(
            CVAnalysisResult.cv_hash == cv_id,
            CVAnalysisResult.job_posting_id == job_id
        ).first()

        if existing_result:
            print("Result already exists. Skipping analysis.")
            output_key = existing_result.s3_key
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Analysis already existed. No re-processing.",
                    "result_s3_path": f"s3://{bucket}/{output_key}",
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

        # Get job description from DB
        job_posting = session.query(JobPosting).filter(
            JobPosting.posting_id == job_id,
            JobPosting.created_by_user_id == user_id
        ).first()

        if not job_posting:
            return {"statusCode": 404,
                    "body": json.dumps({"error": "Job description not found or doesn't belong to the user"})}

        job_description = job_posting.description

        # Extract optional requirements
        experience_level = job_posting.experience_level
        english_level = job_posting.english_level
        industry_experience = job_posting.industry_experience
        contract_type = job_posting.contract_type
        additional_requirements = job_posting.additional_requirements

        # Create a section of optional requirements for the prompt
        additional_requirements_text = ""

        # The rest of the prompt logic remains unchanged
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
        parsed_result = json.loads(result_json)

        # If it's a list, take the first element or process each one
        if isinstance(parsed_result, list):
            parsed_result = parsed_result[0]

        parsed_result["name"] = parsed_result["name"].title()

        # Save result to S3
        output_key = f"results/{job_id}/{user_id}#{cv_id}.json"
        s3.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=result_json.encode("utf-8"),
            ContentType="application/json"
        )

        # 1. Save the JobApplication first
        job_application = save_or_update_job_application(
            session=session,
            job_id=job_id,
            user_id=user_id,
            name=parsed_result["name"],
            score=parsed_result["score"],
            upload_key=cv_key,
            cv_hash=cv_id
        )

        # 2. Save the CV analysis result, linked to the JobApplication
        new_analysis_result = CVAnalysisResult(
            job_application_id=job_application.application_id,
            analysis_data=parsed_result,
            s3_key=output_key
        )
        session.add(new_analysis_result)

        # Commit all changes to the database in a single transaction
        session.commit()
        print("✅ Analysis and application data saved to PostgreSQL")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Evaluación completada",
                "result_s3_path": f"s3://{bucket}/{output_key}",
                "recruiter_id": user_id
            })
        }

    except Exception as e:
        print("❌ Error:", str(e))
        # Rollback the session in case of any error
        session.rollback()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        # Close the database session to clean up resources
        session.close()