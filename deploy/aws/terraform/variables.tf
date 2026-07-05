variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
  default     = "whitespace"
}

variable "environment" {
  description = "Deployment environment (dev, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Environment must be dev or prod."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "sa-east-1"
}

# ---------- CDN ----------

variable "use_custom_domain" {
  description = "Whether to create Route 53 + ACM resources for a custom domain"
  type        = bool
  default     = false
}

variable "domain_name" {
  description = "Custom domain name (required if use_custom_domain is true)"
  type        = string
  default     = ""
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone ID (required if use_custom_domain is true)"
  type        = string
  default     = ""
}

# ---------- Monitoring ----------

variable "budget_limit_usd" {
  description = "Monthly budget alert threshold in USD"
  type        = string
  default     = "10.0"
}

variable "budget_notification_email" {
  description = "Email for budget alert notifications"
  type        = string
  default     = ""
}

# ---------- Secrets ----------

variable "clerk_secret_key" {
  description = "Clerk secret key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "stripe_secret_key" {
  description = "Stripe secret key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "clerk_webhook_secret" {
  description = "Clerk webhook signing secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openrouter_api_key" {
  description = "OpenRouter API key (server-side for SaaS fallback)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "exa_api_key" {
  description = "Exa search API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "firecrawl_api_key" {
  description = "Firecrawl API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "langsmith_api_key" {
  description = "LangSmith API key"
  type        = string
  sensitive   = true
  default     = ""
}
