variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "lambda_build_dir" {
  description = "Path to directory containing Lambda zip packages"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for Lambda functions needing VPC access"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for VPC-attached Lambdas"
  type        = list(string)
}

variable "fargate_security_group_id" {
  description = "Security group for VPC-attached Lambdas"
  type        = string
}

variable "results_bucket_name" {
  description = "S3 bucket name for search results"
  type        = string
}

variable "results_bucket_arn" {
  description = "S3 bucket ARN for search results"
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group for Lambda"
  type        = string
}

variable "clerk_jwks_url" {
  description = "Clerk JWKS URL for the authoriser"
  type        = string
  default     = ""
}

variable "clerk_issuer" {
  description = "Clerk issuer URL for the authoriser"
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}
