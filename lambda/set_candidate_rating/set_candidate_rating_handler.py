import json
import os
import boto3
from sqlalchemy import and_

# Import ORM session handler and models
from db_handler import get_session
from models import JobApplication, JobPosting

# CORS headers
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def lambda_handler(event, context):
    # Handle CORS preflight request
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": CORS_HEADERS
        }

    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user_id = claims.get("sub")
    if not user_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Usuario no autenticado"})
        }

    # Get a database session
    session = get_session()

    try:
        print("🔍 Event:", event)
        body_str = event.get("body", "")
        body = json.loads(body_str) if body_str else {}

        job_id = body.get("jobId")
        candidate_cv_hash = body.get("cvId")  # cvId is the CV's unique hash
        rating = body.get("valoracion")

        print(f" Payload recibido: jobId={job_id}, cvId={candidate_cv_hash}, valoracion={rating}")

        if not job_id or not candidate_cv_hash or rating is None:
            print("⚠ Parámetros faltantes")
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Faltan parámetros obligatorios"})
            }

        # New: Use a single query to get the JobApplication and verify ownership
        job_application = session.query(JobApplication).join(JobPosting).filter(
            and_(
                JobApplication.job_posting_id == job_id,
                JobApplication.cv_hash == candidate_cv_hash,
                JobPosting.created_by_user_id == user_id
            )
        ).first()

        if not job_application:
            print("🚫 No se encontró la postulación o el usuario no es el dueño")
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "El candidato no pertenece al job o no tienes permiso"})
            }

        # Update ratings
        job_application.valoracion = rating

        # Commit the changes to the database
        session.commit()

        print(f"✅ Update OK. valoracion actualizada a: {job_application.valoracion}")

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({"message": "Rating actualizado correctamente"})
        }

    except json.JSONDecodeError as jde:
        print(f"❌ JSON inválido: {str(jde)}")
        session.rollback()
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Error al procesar el JSON"})
        }

    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")
        session.rollback()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        session.close()