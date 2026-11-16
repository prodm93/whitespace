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
  default     = "us-east-1"
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

# ---------- Sign-in (Clerk) ----------

variable "clerk_jwks_url" {
  description = "Clerk JWKS URL: the Frontend API URL followed by /.well-known/jwks.json. Found in the Clerk dashboard, API keys page."
  type        = string

  validation {
    condition     = startswith(var.clerk_jwks_url, "https://")
    error_message = "clerk_jwks_url must start with https://."
  }
}

variable "clerk_issuer" {
  description = "Clerk issuer: the Frontend API URL, no trailing slash. Found in the Clerk dashboard, API keys page."
  type        = string

  validation {
    condition     = startswith(var.clerk_issuer, "https://")
    error_message = "clerk_issuer must start with https://."
  }

  validation {
    condition     = !endswith(var.clerk_issuer, "/")
    error_message = "clerk_issuer must not end with a slash; the authoriser compares the issuer exactly."
  }
}

variable "clerk_authorized_parties" {
  description = "Origins allowed to sign in: the addresses the browser shows for the app, no trailing slash, for example https://app.example.com or http://localhost:3000."
  type        = list(string)

  validation {
    condition     = length(var.clerk_authorized_parties) > 0
    error_message = "clerk_authorized_parties must name at least one origin."
  }

  validation {
    condition = alltrue([
      for origin in var.clerk_authorized_parties :
      startswith(origin, "https://") || can(regex("^http://localhost(:[0-9]+)?$", origin))
    ])
    error_message = "Each origin in clerk_authorized_parties must start with https://, or be http://localhost with an optional port."
  }

  validation {
    condition     = alltrue([for origin in var.clerk_authorized_parties : !endswith(origin, "/")])
    error_message = "No origin in clerk_authorized_parties may end with a slash; the browser sends its origin without one."
  }
}

# ---------- Pipeline ----------

variable "pipeline_image_uri" {
  description = "Full ECR image URI with immutable tag for the pipeline orchestrator"
  type        = string

  validation {
    condition     = !can(regex("@sha256:", var.pipeline_image_uri))
    error_message = "pipeline_image_uri must use a tagged reference, not a digest."
  }
}
