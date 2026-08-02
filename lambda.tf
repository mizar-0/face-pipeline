# Zip up the Lambda code folder so it can be uploaded to AWS
data "archive_file" "ingestion_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/ingestion"
  output_path = "${path.module}/build/ingestion.zip"
}

resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project_name}-ingestion"
  role          = aws_iam_role.ingestion_lambda_role.arn

  filename         = data.archive_file.ingestion_zip.output_path
  source_code_hash = data.archive_file.ingestion_zip.output_base64sha256

  handler = "handler.lambda_handler"  # filename.function_name
  runtime = "python3.12"
  timeout = 30                        # seconds before AWS kills the execution
  memory_size = 256                   # MB, affects both speed and cost
}

# Allow S3 to invoke this Lambda specifically (permission is separate
# from the IAM role — this is Lambda's own resource-based policy)
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_photos.arn
}

# Wire up the actual trigger: "whenever an object is created in
# raw_photos, invoke the ingestion Lambda"
resource "aws_s3_bucket_notification" "raw_photos_trigger" {
  bucket = aws_s3_bucket.raw_photos.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion.arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke]
}
