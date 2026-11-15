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
