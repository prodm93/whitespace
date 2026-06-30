output "upload_bucket_name" {
  description = "Uploads S3 bucket name"
  value       = aws_s3_bucket.uploads.id
}

output "upload_bucket_arn" {
  description = "Uploads S3 bucket ARN"
  value       = aws_s3_bucket.uploads.arn
}

output "results_bucket_name" {
  description = "Job results S3 bucket name"
  value       = aws_s3_bucket.results.id
}

output "results_bucket_arn" {
  description = "Job results S3 bucket ARN"
  value       = aws_s3_bucket.results.arn
}

output "checkpoints_bucket_name" {
  description = "LangGraph checkpoint overflow S3 bucket name"
  value       = aws_s3_bucket.checkpoints.id
}

output "checkpoints_bucket_arn" {
  description = "LangGraph checkpoint overflow S3 bucket ARN"
  value       = aws_s3_bucket.checkpoints.arn
}

output "usage_table_name" {
  description = "DynamoDB usage tracking table name"
  value       = aws_dynamodb_table.usage.name
}

output "usage_table_arn" {
  description = "DynamoDB usage tracking table ARN"
  value       = aws_dynamodb_table.usage.arn
}

output "jobs_table_name" {
  description = "DynamoDB jobs table name"
  value       = aws_dynamodb_table.jobs.name
}

output "jobs_table_arn" {
  description = "DynamoDB jobs table ARN"
  value       = aws_dynamodb_table.jobs.arn
}

output "checkpoints_table_name" {
  description = "DynamoDB LangGraph checkpoints table name"
  value       = aws_dynamodb_table.checkpoints.name
}

output "checkpoints_table_arn" {
  description = "DynamoDB LangGraph checkpoints table ARN"
  value       = aws_dynamodb_table.checkpoints.arn
}
