# Face Pipeline

An AWS serverless pipeline for uploading photos, detecting faces, grouping matching faces, and browsing the resulting people and face thumbnails.

## Architecture

```text
Client
  │
  ├─ POST /uploads ───────────────► API Gateway ─► API Lambda
  │                                      │             │
  │                                      └── presigned S3 PUT URL
  │
  └─ uploads image directly to S3 ─► Raw photos bucket
												  │
												  └─ S3 ObjectCreated event
													  ▼
											  Ingestion Lambda
												  │
				 ┌────────────────────────┼────────────────────────┐
				 ▼                        ▼                        ▼
			 Rekognition              Pillow              DynamoDB tables
		 detect/search/index      crop face images       photos/people/appearances
				 │                        │                        │
				 └──────────────► Processed thumbnails ◄──────────┘
```

Terraform provisions the AWS infrastructure, Lambda functions, IAM policies, DynamoDB tables, S3 buckets, API Gateway HTTP API, and a Rekognition collection.

## Features

- Generates presigned upload URLs so image bytes bypass API Gateway and Lambda.
- Detects faces with Amazon Rekognition.
- Searches an existing Rekognition collection and indexes new faces when no match is found.
- Crops detected faces with Pillow and stores thumbnails in a processed S3 bucket.
- Stores photo, person, and appearance metadata in DynamoDB.
- Provides API endpoints for listing people and their thumbnails.
- Uses separate IAM roles for the API and ingestion Lambdas.
- Builds a Python 3.12-compatible Pillow Lambda layer.

## Repository layout

| Path | Purpose |
| --- | --- |
| `*.tf` | Terraform infrastructure and IAM configuration |
| `lambda/api/handler.py` | API Lambda and presigned URL generation |
| `lambda/ingestion/handler.py` | S3-triggered face processing |
| `lambda_layers/pillow/` | Locally generated Pillow Lambda layer; ignored by Git |
| `build/` | Generated Lambda ZIP files; ignored by Git |
| `.github/workflows/deploy.yml` | CI validation and deployment workflow |
| `test/` | Sample image files used for manual testing |

## Prerequisites

- An AWS account and permissions to create S3, Lambda, API Gateway, DynamoDB, IAM, and Rekognition resources.
- Terraform 1.9 or newer.
- AWS CLI installed and authenticated with credentials supplied through your normal secure credential mechanism.
- Python 3.12 and `pip`.
- A Linux-compatible Pillow build for the Lambda layer. The CI workflow builds it from a manylinux wheel.
- An S3 bucket for the Terraform backend, configured in `main.tf`, before running `terraform init`.

Do not commit credentials, `.tfvars` files, Terraform state, presigned URLs, or private images. The repository `.gitignore` excludes the generated layer, build artifacts, and state files.

## Configuration

The supported Terraform variables are:

| Variable | Default | Description |
| --- | --- | --- |
| `aws_region` | `us-east-1` | AWS region for the deployment |
| `project_name` | `facepipeline` | Prefix used for resource names |

You can provide overrides through a local, untracked `.tfvars` file or Terraform command-line variables. Never put credentials in Terraform variables.

The ingestion Lambda also supports the optional `FACE_MATCH_THRESHOLD` environment variable. It defaults to `95` when not configured.

## Local deployment

1. Configure the Terraform backend in `main.tf` for an S3 bucket you control.
2. Authenticate the AWS CLI without placing keys in the repository.
3. Build the Pillow layer for Python 3.12 and the Lambda target platform. For example, install Pillow into `lambda_layers/pillow/python` using a Linux-compatible wheel; the workflow file contains the CI build settings.
4. From the repository root, run Terraform initialization, formatting, validation, plan, and apply.
5. Read the generated endpoint and resource names from Terraform outputs.

Terraform creates the Rekognition collection through the AWS CLI because the AWS Terraform provider does not provide a native collection resource. Therefore, the AWS CLI must be available to the machine running `terraform apply` and `terraform destroy`.

## API

Set `API_URL` to the `api_url` Terraform output. Do not paste a real endpoint or a presigned URL into source control.

### Create an upload URL

`POST /uploads`

Request body:

```json
{
  "filename": "photo.jpg"
}
```

The response contains a short-lived presigned S3 PUT URL, an object key, and the destination bucket. Upload the image bytes to that URL with the expected image content type.

### List recognized people

`GET /people`

Returns up to 100 people, sorted by the number of photos in which each person appears. Thumbnail URLs are presigned and expire after one hour.

### List photos for a person

`GET /people/{person_id}/photos`

Returns the photos associated with a person, including thumbnail URLs and face-match confidence values.

Processing is asynchronous: wait for the S3 event and ingestion Lambda to finish before expecting a newly uploaded image to appear in the API.

## Data model

- **Photos**: one record per uploaded image, including its source S3 location, face count, and generated thumbnail keys.
- **People**: one record per Rekognition face ID, including a representative thumbnail and photo count.
- **Appearances**: one record per person/photo pair, including the bounding box, confidence, and thumbnail key.

All three DynamoDB tables use on-demand billing. The raw image remains in the raw S3 bucket; cropped face images are written to the processed S3 bucket.

## CI/CD

The GitHub Actions workflow:

- Builds the Pillow layer on Ubuntu for Python 3.12.
- Runs `terraform fmt -check -recursive`, `terraform init`, `terraform validate`, and `terraform plan`.
- Applies Terraform only for pushes to the `main` branch.
- Uses GitHub Actions secrets for AWS authentication; those values must be configured in repository settings and must never be copied into this README or committed files.


## Cleanup

Run `terraform destroy` from an authenticated environment when the deployment is no longer needed. This also attempts to delete the Rekognition collection through the AWS CLI. Verify retention and deletion requirements for stored images and metadata separately.

