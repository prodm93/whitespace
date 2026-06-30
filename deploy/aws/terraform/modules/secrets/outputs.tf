output "parameter_arns" {
  description = "ARNs of all SSM parameters"
  value       = [for p in aws_ssm_parameter.secret : p.arn]
}

output "parameter_names" {
  description = "Map of logical key to SSM parameter name"
  value       = { for k, p in aws_ssm_parameter.secret : k => p.name }
}
