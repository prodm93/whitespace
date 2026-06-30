output "cloudfront_domain" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend build artifacts"
  value       = aws_s3_bucket.frontend.id
}

output "frontend_bucket_arn" {
  description = "S3 bucket ARN for frontend build artifacts"
  value       = aws_s3_bucket.frontend.arn
}
