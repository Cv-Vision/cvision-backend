FROM public.ecr.aws/lambda/python:3.9

COPY requirements.txt .
RUN pip install -r requirements.txt -t .

COPY set_candidate_rating_handler.py ./

CMD ["set_candidate_rating_handler.lambda_handler"]
