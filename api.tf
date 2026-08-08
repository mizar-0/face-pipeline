# Zip up the API lambda code
data "archive_file" "api_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/api"
  output_path = "${path.module}/build/api.zip"
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-api"
  role          = aws_iam_role.api_lambda_role.arn

  filename         = data.archive_file.api_zip.output_path
  source_code_hash = data.archive_file.api_zip.output_base64sha256

  handler     = "handler.lambda_handler"
  runtime     = "python3.12"
  timeout     = 15
  memory_size = 256

  environment {
    variables = {
      PEOPLE_TABLE       = aws_dynamodb_table.people.name
      APPEARANCES_TABLE  = aws_dynamodb_table.appearances.name
      PHOTOS_TABLE       = aws_dynamodb_table.photos.name
      PROCESSED_BUCKET   = aws_s3_bucket.processed_photos.bucket
      RAW_BUCKET         = aws_s3_bucket.raw_photos.bucket
    }
  }
}

# --- API Gateway (HTTP API -- simpler and cheaper than REST API,
# sufficient for a small read-only JSON API like this one) ---

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
}

# AWS_PROXY integration means API Gateway forwards the entire request
# to Lambda as-is, and returns whatever Lambda returns -- the routing
# logic (which path was hit) lives in your Python code, not in Terraform.
resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_people" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /people"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

resource "aws_apigatewayv2_route" "get_person_photos" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /people/{person_id}/photos"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

resource "aws_apigatewayv2_route" "post_uploads" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /uploads"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# $default stage with auto_deploy means any route/integration change
# goes live immediately on apply, no separate manual deployment step
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

# Allow API Gateway specifically to invoke this Lambda -- same pattern
# as the S3 invoke permission, different principal
resource "aws_lambda_permission" "allow_apigateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
