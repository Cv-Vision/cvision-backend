FROM public.ecr.aws/lambda/python:3.9

COPY requirements.txt .
RUN pip install -r requirements.txt -t .

COPY candidate_profile_handler.py ./

CMD ["candidate_profile_handler.lambda_handler"]