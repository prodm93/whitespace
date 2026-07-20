output "orchestrate_queue_url" {
  description = "Orchestrate queue URL"
  value       = aws_sqs_queue.main["orchestrate"].url
}

output "orchestrate_queue_arn" {
  description = "Orchestrate queue ARN"
  value       = aws_sqs_queue.main["orchestrate"].arn
}

output "orchestrate_queue_name" {
  description = "Orchestrate queue name"
  value       = aws_sqs_queue.main["orchestrate"].name
}
