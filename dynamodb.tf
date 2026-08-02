# Tracks which faces appear in which photo
resource "aws_dynamodb_table" "photos" {
  name         = "${var.project_name}-photos"
  billing_mode = "PAY_PER_REQUEST"  # no capacity planning needed, pay only per request
  hash_key     = "photo_id"

  attribute {
    name = "photo_id"
    type = "S"  # S = string
  }
}

# One row per unique person (a Rekognition face id maps here)
resource "aws_dynamodb_table" "people" {
  name         = "${var.project_name}-people"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "person_id"

  attribute {
    name = "person_id"
    type = "S"
  }
}

# Which photos a given person appears in
resource "aws_dynamodb_table" "appearances" {
  name         = "${var.project_name}-appearances"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "person_id"
  range_key    = "photo_id"

  attribute {
    name = "person_id"
    type = "S"
  }

  attribute {
    name = "photo_id"
    type = "S"
  }
}
