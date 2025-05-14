Este repositorio contiene las funciones **AWS Lambda** utilizadas por la plataforma **CVision** para el análisis automatizado de CVs y su integración con servicios como **Textract**, y **DynamoDB**.


---

## Funciones Lambda

### `s3_to_textract_handler`

- **Trigger**: Evento de `ObjectCreated` en un bucket de S3 (cuando se sube un CV).
- **Responsabilidad**: Llamar a Textract para extraer el texto del PDF.
- **Output**: Invoca programáticamente a `cv_processor` con el texto extraído.

### `cv_processor`

- **Trigger**: Llamado por la Lambda anterior (o directamente mediante API Gateway).
- **Responsabilidad**:
  - Procesar el texto con una API LLM para extraer campos clave.
  - Calcular similitud entre CV y Job Description.
  - Guardar el resultado estructurado en DynamoDB.

---

## Despliegue

El despliegue se realiza automáticamente mediante GitHub Actions (`.github/workflows/`), que:

1. Instala dependencias.
2. Empaqueta cada Lambda.
3. Sube el código a AWS.
4. Opcional: configura los triggers si no existen.

> ⚠️ Para configurar correctamente los permisos, se requiere una política IAM con permisos para Lambda, S3, Textract, Bedrock y DynamoDB.

---

## Requisitos

- Python 3.13
- AWS CLI configurado
- Acceso a:
  - Amazon S3
  - Amazon Textract
  - API del LLM con su respectiva key
  - DynamoDB
  - API Gateway (para exponer `cv_processor`, opcional)

---

## Pruebas

Podés usar `scripts/local_test.py` o Postman para enviar eventos simulados de forma local o manual.

---

## ✍Contribución

Este proyecto es parte de la plataforma **CVision**. Si necesitás agregar una nueva función Lambda:

1. Creá un nuevo subdirectorio bajo `lambda/`.
2. Incluí `nombre-de-funcion_handler.py` y `requirements.txt`.
3. Agregá el deploy en el workflow correspondiente.
4. Validá los permisos necesarios (IAM y triggers).
