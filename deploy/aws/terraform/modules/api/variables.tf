variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "vpc_id" {
  description = "VPC ID for VPC Link"
  type        = string
}

variable "nlb_arn" {
  description = "NLB ARN for VPC Link to Fargate"
  type        = string
}

variable "nlb_listener_arn" {
  description = "NLB listener ARN"
  type        = string
}

variable "container_port" {
  description = "Port the backend listens on"
  type        = number
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for VPC Link"
  type        = list(string)
}

variable "lambda_invoke_arns" {
  description = "Map of route key to Lambda invoke ARN for lightweight routes"
  type        = map(string)
  default     = {}
}

variable "lambda_function_arns" {
  description = "Map of route key to Lambda function ARN (for permissions)"
  type        = map(string)
  default     = {}
}

variable "clerk_jwks_url" {
  description = "Clerk JWKS URL for JWT validation"
  type        = string
  default     = ""
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
