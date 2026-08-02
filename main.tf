terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Bucket for original uploaded photos
resource "aws_s3_bucket" "raw_photos" {
  bucket = "${var.project_name}-raw-${random_id.suffix.hex}"
}

# Bucket for cropped face thumbnails
resource "aws_s3_bucket" "processed_photos" {
  bucket = "${var.project_name}-processed-${random_id.suffix.hex}"
}

# S3 bucket names must be globally unique across ALL AWS accounts,
# so we append a random suffix to avoid collisions
resource "random_id" "suffix" {
  byte_length = 4
}