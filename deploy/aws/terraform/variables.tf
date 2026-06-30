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

# ---------- Networking ----------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones"
  type        = number
  default     = 2
}

# ---------- Compute ----------

variable "fargate_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "fargate_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 2048
}

variable "container_port" {
  description = "Port the backend container listens on"
  type        = number
  default     = 8000
}

variable "fargate_min_capacity" {
  description = "Minimum Fargate task count"
  type        = number
  default     = 0
}

variable "fargate_max_capacity" {
  description = "Maximum Fargate task count"
  type        = number
  default     = 2
}

variable "scale_down_cron" {
  description = "Cron expression for scheduled scale-down (UTC)"
  type        = string
  default     = "cron(0 4 * * ? *)"
}

variable "scale_up_cron" {
  description = "Cron expression for scheduled scale-up (UTC)"
  type        = string
  default     = "cron(0 12 * * ? *)"
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
