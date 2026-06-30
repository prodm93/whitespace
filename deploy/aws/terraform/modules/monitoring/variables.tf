variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "budget_limit_usd" {
  description = "Monthly budget alert threshold in USD"
  type        = string
}

variable "budget_notification_email" {
  description = "Email for budget alert notifications"
  type        = string
}

variable "sqs_queue_names" {
  description = "SQS queue names to monitor"
  type        = list(string)
  default     = []
}

variable "ecs_cluster_name" {
  description = "ECS cluster name for dashboard"
  type        = string
  default     = ""
}

variable "ecs_service_name" {
  description = "ECS service name for dashboard"
  type        = string
  default     = ""
}
