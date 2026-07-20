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

variable "results_bucket_name" {
  description = "S3 bucket name for job results"
  type        = string
}

variable "results_bucket_arn" {
  description = "S3 bucket ARN for job results"
  type        = string
}

variable "checkpoints_bucket_name" {
  description = "S3 bucket name for checkpoint overflow"
  type        = string
}

variable "checkpoints_bucket_arn" {
  description = "S3 bucket ARN for checkpoint overflow"
  type        = string
}

variable "uploads_bucket_name" {
  description = "S3 bucket name for user file uploads"
  type        = string
}

variable "uploads_bucket_arn" {
  description = "S3 bucket ARN for user file uploads"
  type        = string
}

variable "checkpoints_table_name" {
  description = "DynamoDB table name for LangGraph checkpoints"
  type        = string
}

variable "jobs_table_name" {
  description = "DynamoDB jobs table name"
  type        = string
}

variable "jobs_table_arn" {
  description = "DynamoDB jobs table ARN"
  type        = string
}

variable "sessions_table_name" {
  description = "DynamoDB session store table name"
  type        = string
}

variable "sessions_table_arn" {
  description = "DynamoDB session store table ARN"
  type        = string
}

variable "usage_table_name" {
  description = "DynamoDB usage tracking table name"
  type        = string
}

variable "usage_table_arn" {
  description = "DynamoDB usage tracking table ARN"
  type        = string
}

variable "ecr_repository_url" {
  description = "ECR repository URL for the pipeline orchestrator image"
  type        = string
}

variable "orchestrate_queue_arn" {
  description = "SQS orchestrate queue ARN"
  type        = string
}

variable "orchestrate_queue_url" {
  description = "SQS orchestrate queue URL"
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
