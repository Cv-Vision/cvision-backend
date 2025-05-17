import json
import uuid
from datetime import datetime
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('JobDescriptionsTable')

REQUIRED_FIELDS = ["title", "description", "location", "level", "skills"]

def createJobDescriptionHandler(event, context):
    try:
        # Parsear el body
        body = json.loads(event.get("body", "{}"))

        # Validar campos requeridos
        missing_fields = [field for field in REQUIRED_FIELDS if field not in body]
        if missing_fields:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"Missing fields: {', '.join(missing_fields)}"})
            }

        # Obtener user_id desde el token
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        user_id = claims.get("sub")  # 'sub' es el user_id único en Cognito

        if not user_id:
            return {
                "statusCode": 401,
                "body": json.dumps({"message": "Unauthorized - user_id not found"})
            }

        # Generar UUID y timestamp
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        # Construir ítem para DynamoDB
        item = {
            "pk": f"JD#{job_id}",
            "sk": f"USER#{user_id}",
            "created_at": created_at,
            "title": body["title"],
            "description": body["description"],
            "location": body["location"],
            "level": body["level"],
            "skills": body["skills"],  # Puede ser lista o string, depende de tu modelo
        }

        # Guardar en DynamoDB
        table.put_item(Item=item)

        # Devolver respuesta
        return {
            "statusCode": 201,
            "body": json.dumps({"job_id": job_id})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Internal server error: {str(e)}"})
        }
