terraform {
  backend "s3" {
    bucket         = "whitespace-terraform-state"
    key            = "terraform.tfstate"
    region         = "sa-east-1"
    dynamodb_table = "whitespace-terraform-locks"
    encrypt        = true
  }
}
