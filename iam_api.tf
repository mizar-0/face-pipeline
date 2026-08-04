
data "aws_iam_policy_document" "api_lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api_lambda_role" {
  name               = "${var.project_name}-api-role"
  assume_role_policy = data.aws_iam_policy_document.api_lambda_trust.json
}

# --- Permission policy: WHAT the role can do once assumed ---
# Deliberately read-only -- this Lambda serves client requests, it never
# writes anything. A separate, narrower role from the ingestion Lambda's,
# even though both eventually touch the same tables/bucket.
data "aws_iam_policy_document" "api_permissions" {
  # Read from the people and appearances tables.
  # Scan is included because /people lists everyone (small table, scan is
  # fine here); Query is for the /people/{id}/photos lookup by person_id.
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan"
    ]
    resources = [
      aws_dynamodb_table.people.arn,
      aws_dynamodb_table.appearances.arn
    ]
  }

  # Needed to generate presigned URLs for thumbnails -- generating a
  # presigned URL is a local SDK operation, but the calling identity's
  # permissions are what the URL is ultimately allowed to do once used.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.processed_photos.arn}/*"]
  }
}

resource "aws_iam_role_policy" "api_permissions" {
  name   = "${var.project_name}-api-permissions"
  role   = aws_iam_role.api_lambda_role.id
  policy = data.aws_iam_policy_document.api_permissions.json
}

# Same AWS-managed policy as the ingestion role, for CloudWatch logging
resource "aws_iam_role_policy_attachment" "api_logging" {
  role       = aws_iam_role.api_lambda_role.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
