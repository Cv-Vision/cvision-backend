import json
import os
import boto3
import decimal

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["JOB_APPLICATIONS_TABLE"])

# CORS headers
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
}

# Para poder loguear valores Decimal
def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError

def lambda_handler(event, context):
    print(" Lambda ejecutada")
    print(" Evento completo:")
    print(json.dumps(event, indent=2, default=str))

    try:
        #  Auth por Cognito
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

        #  Body recibido
        body_str = event.get("body", "")
        body = json.loads(body_str) if body_str else {}

        job_id = body.get("jobId")
        candidate_id = body.get("cvId")
        rating = body.get("valoracion")

        print(f" Payload recibido: jobId={job_id}, cvId={candidate_id}, valoracion={rating}")

        if not job_id or not candidate_id or rating is None:
            print("⚠ Parámetros faltantes")
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Faltan parámetros obligatorios"})
            }

        # Armar claves
        job_pk = f"JD#{job_id}" if not job_id.startswith("JD#") else job_id
        candidate_sk = f"CV#{candidate_id}" if not candidate_id.startswith("CV#") else candidate_id

        print(f"🔑 Claves: pk={job_pk}, sk={candidate_sk}")

        # 🔍 Obtener ítem
        response = table.get_item(Key={"pk": job_pk, "sk": candidate_sk})
        print(f" Respuesta de get_item: {json.dumps(response, indent=2, default=decimal_default)}")

        if "Item" not in response:
            print("🚫 No se encontró el ítem")
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "El candidato no pertenece al job"})
            }

        # Actualizar valoracion
        update_response = table.update_item(
            Key={"pk": job_pk, "sk": candidate_sk},
            UpdateExpression="SET valoracion = :r",
            ExpressionAttributeValues={":r": str(rating)},
            ReturnValues="UPDATED_NEW"
        )

        print(f"✅ Update OK: {json.dumps(update_response, indent=2)}")

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
