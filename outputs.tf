output "raw_bucket_name" {
  value = aws_s3_bucket.raw_photos.bucket
}

output "processed_bucket_name" {
  value = aws_s3_bucket.processed_photos.bucket
}

output "photos_table_name" {
  value = aws_dynamodb_table.photos.name
}

output "people_table_name" {
  value = aws_dynamodb_table.people.name
}

output "appearances_table_name" {
  value = aws_dynamodb_table.appearances.name
}