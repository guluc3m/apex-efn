# Remote state is NOT configured. Before the first `terraform init` against a real account:
#   1. Create the state bucket (versioning + SSE-KMS + public access blocked) and a lock table
#      (DynamoDB, partition key "LockID") outside this repo.
#   2. Uncomment the block below and fill in the placeholders. Never commit real bucket names.
#
# terraform {
#   backend "s3" {
#     bucket         = "<state-bucket>"
#     key            = "trato/staging/terraform.tfstate"
#     region         = "<region>"
#     dynamodb_table = "<lock-table>"
#     encrypt        = true
#   }
# }
