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

output "pipeline_orchestrator_invoke_arn" {
  description = "Pipeline orchestrator Lambda invoke ARN"
  value       = aws_lambda_function.pipeline_orchestrator.invoke_arn
}

output "pipeline_orchestrator_function_arn" {
  description = "Pipeline orchestrator Lambda function ARN"
  value       = aws_lambda_function.pipeline_orchestrator.arn
}

output "orchestrate_enqueue_invoke_arn" {
  description = "Orchestrate enqueue Lambda invoke ARN"
  value       = aws_lambda_function.orchestrate_enqueue.invoke_arn
}

output "orchestrate_enqueue_function_arn" {
  description = "Orchestrate enqueue Lambda function ARN"
  value       = aws_lambda_function.orchestrate_enqueue.arn
}

output "upload_url_invoke_arn" {
  description = "Upload URL Lambda invoke ARN"
  value       = aws_lambda_function.upload_url.invoke_arn
}

output "upload_url_function_arn" {
  description = "Upload URL Lambda function ARN"
  value       = aws_lambda_function.upload_url.arn
}

output "runs_reader_invoke_arn" {
  description = "Runs reader Lambda invoke ARN"
  value       = aws_lambda_function.runs_reader.invoke_arn
}

output "runs_reader_function_arn" {
  description = "Runs reader Lambda function ARN"
  value       = aws_lambda_function.runs_reader.arn
}
