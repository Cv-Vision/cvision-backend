FROM public.ecr.aws/lambda/python:3.9

# Copiamos el handler y requirements
COPY get-cvs-analysis-results_handler.py ./
COPY requirements.txt ./

# Instalamos las dependencias
RUN pip install -r requirements.txt

# Entry point para AWS Lambda
CMD ["get-cvs-analysis-results_handler_handler.lambda_handler"]
