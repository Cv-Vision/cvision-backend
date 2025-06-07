# Use the official Python image from Docker Hub
FROM python:3.13-slim

# Establish the environment variable for Python to not buffer stdout and stderr
ENV PYTHONUNBUFFERED=1

# Copy the requirements file into the container
# The path is relative to the build context (cvision-backend/)
COPY lambda/cv_batch_invoker/requirements.txt .

# Install the required packages inside the container
RUN pip install --no-cache-dir -r requirements.txt
