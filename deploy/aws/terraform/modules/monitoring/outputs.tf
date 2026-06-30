output "fargate_log_group_name" {
  description = "CloudWatch log group name for Fargate"
  value       = aws_cloudwatch_log_group.fargate.name
}

output "lambda_log_group_name" {
  description = "CloudWatch log group name for Lambda"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "alarms_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  value       = aws_sns_topic.alarms.arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard name"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}
