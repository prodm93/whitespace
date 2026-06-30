variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "use_custom_domain" {
  description = "Whether to create Route 53 + ACM resources"
  type        = bool
}

variable "domain_name" {
  description = "Custom domain name"
  type        = string
  default     = ""
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone ID"
  type        = string
  default     = ""
}

variable "api_gateway_endpoint" {
  description = "API Gateway endpoint for /api/* origin"
  type        = string
  default     = ""
}
