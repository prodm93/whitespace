output "api_id" {
  description = "API Gateway ID"
  value       = aws_apigatewayv2_api.main.id
}

output "api_endpoint" {
  description = "API Gateway invoke URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_execution_arn" {
  description = "API Gateway execution ARN"
  value       = aws_apigatewayv2_api.main.execution_arn
}
