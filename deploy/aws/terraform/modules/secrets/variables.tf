variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "clerk_secret_key" {
  type      = string
  sensitive = true
}

variable "stripe_secret_key" {
  type      = string
  sensitive = true
}

variable "clerk_webhook_secret" {
  type      = string
  sensitive = true
}

variable "openrouter_api_key" {
  type      = string
  sensitive = true
}

variable "exa_api_key" {
  type      = string
  sensitive = true
}

variable "firecrawl_api_key" {
  type      = string
  sensitive = true
}

variable "langsmith_api_key" {
  type      = string
  sensitive = true
}
