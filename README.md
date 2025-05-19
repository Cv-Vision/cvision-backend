# CVision Backend

This repository contains the AWS Lambda functions used by the CVision platform for automated CV analysis and integration with services like Textract and DynamoDB.

---

## 🧠 Lambda Functions

### `s3_to_textract_handler`

- **Trigger**: S3 `ObjectCreated` event (when a CV is uploaded).
- **Responsibility**: Calls Textract to extract text from the PDF.
- **Output**: Invokes `cv_processor` Lambda with the extracted text.

### `cv_processor`

- **Trigger**: Invoked by `s3_to_textract_handler` or directly via API Gateway.
- **Responsibilities**:
  - Use an LLM API to extract structured data from the CV text.
  - Calculate semantic similarity with a Job Description.
  - Store the result in DynamoDB.
 
### `createJobDescriptionHandler`

- **Trigger**: HTTP POST via API Gateway.
- **Responsibility**: Creates and stores a Job Description in DynamoDB.
- **Security**: Requires authentication via AWS Cognito.
- **Input**: JSON with title, description, location, level, skills.
- **Output**: UUID (`job_id`) of the stored job description.

### `generate_presigned_url_handler`

- **Trigger**: HTTP POST via API Gateway.
- **Responsibility**: Generates pre-signed S3 upload URLs for one or more PDF files under a specific `job_id`.
- **Security**: Requires authentication via AWS Cognito.
- **Input**: JSON with `job_id` and a list of `filenames`.
- **Output**: Array of objects with `filename`, `upload_url`, and `s3_key`.

---

## 🐳 Dependency Management with Docker

This project uses Docker and Docker Compose to create reproducible environments for the Lambda functions.

### Dockerfile

Each `lambda/` subdirectory contains a `Dockerfile` that:

- Uses a lightweight Python 3.13 base image.
- Installs the dependencies listed in `requirements.txt`.

### docker-compose

The `docker-compose.yml` file orchestrates the build process of both Lambda environments.

To build the images with dependencies:

```bash
docker-compose build
```
This will create two images (one per Lambda), containing Python 3.13 and all required libraries.
These images do not include the application code (*_handler.py) and are not designed to run the function directly.

They are intended to:

- Validate and isolate dependency resolution. 
- Be reused as a base in future deployment pipelines.

---
# 🚀 Deployment

Deployment is handled by GitHub Actions workflows:

- Install dependencies (via pip or Docker, depending on setup).

- Package the Lambda code and dependencies.

- Upload the zipped package to AWS Lambda.

- Optionally configure triggers (e.g., S3 notifications).

- ⚠️ Make sure the AWS IAM role has permissions for:
  - Lambda (invoke, logs)
  - S3 (read/write)
  - Textract (document processing)
  - DynamoDB (read/write)
  - Cognito
  - API Gateway (if applicable)

---
# ✍️ Contribution

To add a new Lambda function, create a new folder under lambda/.
- Include:
  - your-function_handler.py 
  - requirements.txt 
  - Dockerfile (copy from existing ones)

- Update docker-compose.yml with a new service. 
- Add a deployment workflow under .github/workflows/. 
- Review IAM permissions and configure necessary AWS triggers.
