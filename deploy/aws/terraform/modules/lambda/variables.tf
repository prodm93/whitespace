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
  description = "S3 bucket name for search results"
  type        = string
}

variable "results_bucket_arn" {
  description = "S3 bucket ARN for search results"
  type        = string
}

variable "checkpoints_bucket_name" {
  description = "S3 bucket name for LangGraph checkpoint overflow"
  type        = string
}

variable "checkpoints_bucket_arn" {
  description = "S3 bucket ARN for LangGraph checkpoint overflow"
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

variable "sessions_table_name" {
  description = "DynamoDB session store table name"
  type        = string
}

variable "ecr_repository_url" {
  description = "ECR repository URL for the pipeline orchestrator image"
  type        = string
}

variable "ingest_queue_arn" {
  description = "SQS ingest queue ARN"
  type        = string
}

variable "gap_council_queue_arn" {
  description = "SQS gap council queue ARN"
  type        = string
}

variable "ideation_council_queue_arn" {
  description = "SQS ideation council queue ARN"
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
