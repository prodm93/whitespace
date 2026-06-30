variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Fargate tasks"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for NLB"
  type        = list(string)
}

variable "fargate_security_group_id" {
  description = "Security group ID for Fargate tasks"
  type        = string
}

variable "ecr_repository_url" {
  description = "ECR repository URL for the backend image"
  type        = string
}

variable "container_port" {
  description = "Port the backend container listens on"
  type        = number
}

variable "cpu" {
  description = "Fargate task CPU units"
  type        = number
}

variable "memory" {
  description = "Fargate task memory in MiB"
  type        = number
}

variable "min_capacity" {
  description = "Minimum Fargate task count"
  type        = number
}

variable "max_capacity" {
  description = "Maximum Fargate task count"
  type        = number
}

variable "scale_down_cron" {
  description = "Cron for scheduled scale-down (UTC)"
  type        = string
}

variable "scale_up_cron" {
  description = "Cron for scheduled scale-up (UTC)"
  type        = string
}

variable "sqs_queue_name" {
  description = "SQS queue name for reactive scaling metric"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "ssm_parameter_arns" {
  description = "ARNs of SSM parameters the task role needs to read"
  type        = list(string)
  default     = []
}

variable "log_group_name" {
  description = "CloudWatch log group name for Fargate"
  type        = string
}
