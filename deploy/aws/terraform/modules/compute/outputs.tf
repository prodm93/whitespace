output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.backend.name
}

output "nlb_arn" {
  description = "Network Load Balancer ARN"
  value       = aws_lb.backend.arn
}

output "nlb_dns_name" {
  description = "Network Load Balancer DNS name"
  value       = aws_lb.backend.dns_name
}

output "nlb_listener_arn" {
  description = "NLB listener ARN"
  value       = aws_lb_listener.backend.arn
}

output "task_role_arn" {
  description = "ECS task IAM role ARN"
  value       = aws_iam_role.task.arn
}
