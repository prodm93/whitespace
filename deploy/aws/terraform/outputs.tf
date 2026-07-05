output "api_gateway_url" {
  description = "API Gateway invoke URL"
  value       = module.api.api_endpoint
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain"
  value       = module.cdn.cloudfront_domain
}

output "ecr_repository_url" {
  description = "ECR repository URL for Docker pushes"
  value       = module.ecr.repository_url
}

output "upload_bucket" {
  description = "S3 bucket for user uploads"
  value       = module.storage.upload_bucket_name
}

output "results_bucket" {
  description = "S3 bucket for job results"
  value       = module.storage.results_bucket_name
}

output "ingest_queue_url" {
  description = "SQS ingest queue URL"
  value       = module.queue.ingest_queue_url
}

output "gap_council_queue_url" {
  description = "SQS gap council queue URL"
  value       = module.queue.gap_council_queue_url
}

output "ideation_council_queue_url" {
  description = "SQS ideation council queue URL"
  value       = module.queue.ideation_council_queue_url
}
