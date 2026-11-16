output "pipeline_secret_arn" {
  description = "ARN of the pipeline function's secret"
  value       = aws_secretsmanager_secret.pipeline.arn
}
