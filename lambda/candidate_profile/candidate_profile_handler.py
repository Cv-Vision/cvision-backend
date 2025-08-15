import json
import os
import boto3
import decimal
from datetime import datetime

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["CANDIDATE_PROFILE_TABLE"])

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError

def validate_profile(data):
    errors = []
    if not data.get("nombre"):
        errors.append("El campo nombre es obligatorio.")
    if not data.get("profesion"):
        errors.append("El campo profesion es obligatorio.")
    for idx, exp in enumerate(data.get("experiencia", [])):
        if not all(k in exp for k in ("empresa", "puesto", "inicio", "fin")):
            errors.append(f"Experiencia #{idx+1} incompleta.")
    for idx, edu in enumerate(data.get("educacion", [])):
        if not all(k in edu for k in ("institucion", "titulo", "inicio", "fin")):
            errors.append(f"Educacion #{idx+1} incompleta.")
    return errors

def lambda_handler(event, context):
    print(" Lambda ejecutada")
    print(" Evento completo:")
    print(json.dumps(event, indent=2, default=str))

    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        user_id = claims.get("sub")
        print(f"🔐 Claims extraídos: {json.dumps(claims, indent=2)}")

        if not user_id:
            print("❌ user_id no presente en claims")
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Unauthorized - user_id not found"})
            }

        body_str = event.get("body", "")
        body = json.loads(body_str) if body_str else {}

        print(f" Payload recibido: {json.dumps(body, indent=2)}")

        errors = validate_profile(body)
        if errors:
            print("⚠ Errores de validación:", errors)
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"errors": errors})
            }

        item = {
            "user_id": user_id,
            "nombre": body["nombre"],
            "profesion": body["profesion"],
            "experiencia": body.get("experiencia", []),
            "educacion": body.get("educacion", []),
            "updated_at": datetime.utcnow().isoformat()
        }

        table.put_item(Item=item)

        print("✅ Perfil guardado/actualizado correctamente")

        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json"
            },
            "body": json.dumps({"message": "Perfil guardado correctamente"})
        }

    except json.JSONDecodeError as jde:
        print(f"❌ JSON inválido: {str(jde)}")
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Error al procesar el JSON"})
        }

    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }