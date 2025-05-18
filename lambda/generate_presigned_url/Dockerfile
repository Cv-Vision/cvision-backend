FROM public.ecr.aws/lambda/python:3.9

# Copiamos el handler y requirements
COPY generate_presigned_url_handler.py ./
COPY requirements.txt ./

# Instalamos las dependencias
RUN pip install -r requirements.txt

# Entry point para AWS Lambda
CMD ["generate_presigned_url_handler.lambda_handler"]
