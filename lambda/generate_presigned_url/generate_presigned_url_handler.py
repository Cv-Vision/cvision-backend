import json
import boto3
import os

s3 = boto3.client('s3', region_name='us-east-2')
dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
job_table = dynamodb.Table('JobDescriptions')
BUCKET_NAME = os.environ.get("BUCKET_NAME", "cvision-cv-bucket")

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))

        print("DEBUG EVENT:", event)
        print("DEBUG BODY:", body)

        job_id = body.get("job_id")
        user_id = body.get("user_id")
        filenames = body.get("filenames")  # Esperamos un array

        if not job_id or not filenames or not isinstance(filenames, list):
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": True
                },
                "body": json.dumps({"error": "Se requiere job_id y un array de filenames"})
            }

        # Validar job_id contra DynamoDB
        print(f"DEBUG: Validando job_id: {job_id}")
        try:
            # Construir la clave primaria usando el formato de la tabla
            pk = f"JD#{job_id}"
            sk = f"USER#{user_id}"

            # Consultar DynamoDB para verificar si existe el job_id
            response = job_table.get_item(
                Key={
                    'pk': pk,
                    'sk': sk
                }
            )

            # Verificar si el item existe
            if 'Item' not in response:
                print(f"ERROR: job_id no encontrado: {job_id}")
                return {
                    "statusCode": 404,
                    "headers": {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Credentials": True
                    },
                    "body": json.dumps({"error": f"El job_id '{job_id}' no existe"})
                }

            print(f"DEBUG: job_id validado correctamente: {job_id}")
        except Exception as e:
            print(f"ERROR: Error al validar job_id: {str(e)}")
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": True
                },
                "body": json.dumps({"error": f"Error al validar job_id: {str(e)}"})
            }

        result = []
        for filename in filenames:
            key = f"uploads/{job_id}/{filename}"
            url = s3.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': key,
                    'ContentType': 'application/pdf'
                },
                ExpiresIn=3600
            )
            result.append({
                "filename": filename,
                "upload_url": url,
                "s3_key": key
            })

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
            "body": json.dumps({
                "job_id": job_id,
                "presigned_urls": result
            })
        }

    except Exception as e:
        print(f"ERROR: Excepción general: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
            "body": json.dumps({"error": str(e)})
        }
