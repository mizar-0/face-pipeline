# --- Trust policy: WHO can assume this role ---
# This says "the Lambda service is allowed to become this role"
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# The role itself, using the trust policy above
resource "aws_iam_role" "ingestion_lambda_role" {
  name               = "${var.project_name}-ingestion-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

# --- Permission policy: WHAT the role can do once assumed ---
data "aws_iam_policy_document" "ingestion_permissions" {
  # Read the uploaded photo from the raw bucket
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.raw_photos.arn}/*"]
  }

  # Write the cropped thumbnail to the processed bucket
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.processed_photos.arn}/*"]
  }

  # Read/write to the three DynamoDB tables
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query"
    ]
    resources = [
      aws_dynamodb_table.photos.arn,
      aws_dynamodb_table.people.arn,
      aws_dynamodb_table.appearances.arn
    ]
  }

  # Call Rekognition to detect/index/search faces
  statement {
    effect = "Allow"
    actions = [
      "rekognition:DetectFaces",
      "rekognition:IndexFaces",
      "rekognition:SearchFacesByImage",
      "rekognition:CreateCollection"
    ]
    resources = ["*"]  # Rekognition doesn't support resource-level scoping for these actions
  }
}

# Attach the custom permission policy to the role
resource "aws_iam_role_policy" "ingestion_permissions" {
  name   = "${var.project_name}-ingestion-permissions"
  role   = aws_iam_role.ingestion_lambda_role.id
  policy = data.aws_iam_policy_document.ingestion_permissions.json
}

# Attach AWS's built-in policy so the Lambda can write logs to CloudWatch
resource "aws_iam_role_policy_attachment" "ingestion_logging" {
  role       = aws_iam_role.ingestion_lambda_role.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
