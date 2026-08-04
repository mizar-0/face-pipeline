# The AWS Terraform provider does not have a native "aws_rekognition_collection"
# resource type (Rekognition support in the provider is limited). So we use
# null_resource + local-exec to run the AWS CLI command directly.
# This is a common escape hatch for the small number of AWS features Terraform's
# provider doesn't cover natively.

resource "null_resource" "rekognition_collection" {
  triggers = {
    collection_id = "${var.project_name}-faces"
    region        = var.aws_region
  }

  provisioner "local-exec" {
    command = "aws rekognition create-collection --collection-id ${self.triggers.collection_id} --region ${self.triggers.region} || echo 'Collection may already exist, continuing'"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws rekognition delete-collection --collection-id ${self.triggers.collection_id} --region ${self.triggers.region} || echo 'Collection already deleted'"
  }
}
