output "ingest_queue_url" {
  description = "Ingest queue URL"
  value       = aws_sqs_queue.main["ingest"].url
}

output "ingest_queue_arn" {
  description = "Ingest queue ARN"
  value       = aws_sqs_queue.main["ingest"].arn
}

output "ingest_queue_name" {
  description = "Ingest queue name"
  value       = aws_sqs_queue.main["ingest"].name
}

output "gap_council_queue_url" {
  description = "Gap council queue URL"
  value       = aws_sqs_queue.main["gap-council"].url
}

output "gap_council_queue_arn" {
  description = "Gap council queue ARN"
  value       = aws_sqs_queue.main["gap-council"].arn
}

output "ideation_council_queue_url" {
  description = "Ideation council queue URL"
  value       = aws_sqs_queue.main["ideation-council"].url
}

output "ideation_council_queue_arn" {
  description = "Ideation council queue ARN"
  value       = aws_sqs_queue.main["ideation-council"].arn
}

output "all_queue_arns" {
  description = "All main queue ARNs"
  value       = [for q in aws_sqs_queue.main : q.arn]
}
