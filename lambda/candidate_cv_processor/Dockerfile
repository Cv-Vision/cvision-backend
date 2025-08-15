FROM public.ecr.aws/lambda/python:3.9

COPY requirements.txt .
RUN pip install -r requirements.txt -t .

COPY candidate_cv_processor_handler.py ./

CMD ["candidate_cv_processor_handler.lambda_handler"]