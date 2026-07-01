output "authoriser_invoke_arn" {
  description = "Authoriser Lambda invoke ARN"
  value       = aws_lambda_function.authoriser.invoke_arn
}

output "authoriser_function_arn" {
  description = "Authoriser Lambda function ARN"
  value       = aws_lambda_function.authoriser.arn
}

output "credential_validator_invoke_arn" {
  description = "Credential validator Lambda invoke ARN"
  value       = aws_lambda_function.credential_validator.invoke_arn
}

output "credential_validator_function_arn" {
  description = "Credential validator Lambda function ARN"
  value       = aws_lambda_function.credential_validator.arn
}

output "search_dispatcher_invoke_arn" {
  description = "Search dispatcher Lambda invoke ARN"
  value       = aws_lambda_function.search_dispatcher.invoke_arn
}

output "search_dispatcher_function_arn" {
  description = "Search dispatcher Lambda function ARN"
  value       = aws_lambda_function.search_dispatcher.arn
}
