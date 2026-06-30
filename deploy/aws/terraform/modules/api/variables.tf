variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "lambda_invoke_arns" {
  description = "Map of route key to Lambda invoke ARN"
  type        = map(string)
  default     = {}
}

variable "lambda_function_arns" {
  description = "Map of route key to Lambda function ARN (for permissions)"
  type        = map(string)
  default     = {}
}

variable "authenticated_routes" {
  description = "Route keys that require Clerk JWT auth"
  type        = list(string)
  default     = []
}

variable "clerk_authoriser_lambda_invoke_arn" {
  description = "Lambda invoke ARN for the Clerk JWT authoriser"
  type        = string
  default     = ""
}

variable "clerk_authoriser_lambda_function_arn" {
  description = "Lambda function ARN for the Clerk JWT authoriser"
  type        = string
  default     = ""
}
