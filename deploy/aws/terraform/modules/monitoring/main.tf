# ---------- Log Groups ----------

resource "aws_cloudwatch_log_group" "fargate" {
  name              = "/ecs/${var.name_prefix}-backend"
  retention_in_days = 14

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fargate-logs"
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}"
  retention_in_days = 14

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-lambda-logs"
  })
}

# ---------- SNS Topic for Alarms ----------

resource "aws_sns_topic" "alarms" {
  name = "${var.name_prefix}-alarms"
  tags = var.common_tags
}

resource "aws_sns_topic_subscription" "email" {
  count = var.budget_notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.budget_notification_email
}

# ---------- Cost Threshold Alarms ----------

resource "aws_cloudwatch_metric_alarm" "cost_20" {
  alarm_name          = "${var.name_prefix}-cost-20usd"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 20
  alarm_description   = "Estimated model cost exceeds $20"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_name = "estimated_cost_usd"
  namespace   = "whitespace"
  statistic   = "Sum"
  period      = 86400

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "cost_50" {
  alarm_name          = "${var.name_prefix}-cost-50usd"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 50
  alarm_description   = "Estimated model cost exceeds $50"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_name = "estimated_cost_usd"
  namespace   = "whitespace"
  statistic   = "Sum"
  period      = 86400

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "cost_100" {
  alarm_name          = "${var.name_prefix}-cost-100usd"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 100
  alarm_description   = "Estimated model cost exceeds $100"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_name = "estimated_cost_usd"
  namespace   = "whitespace"
  statistic   = "Sum"
  period      = 86400

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "cost_140" {
  alarm_name          = "${var.name_prefix}-cost-140usd"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 140
  alarm_description   = "Estimated model cost exceeds $140"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_name = "estimated_cost_usd"
  namespace   = "whitespace"
  statistic   = "Sum"
  period      = 86400

  tags = var.common_tags
}

# ---------- Queue Age Alarm ----------

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  count = length(var.sqs_queue_names) > 0 ? 1 : 0

  alarm_name          = "${var.name_prefix}-queue-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 600
  alarm_description   = "SQS oldest message age exceeds 10 minutes"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_name = "ApproximateAgeOfOldestMessage"
  namespace   = "AWS/SQS"
  statistic   = "Maximum"
  period      = 300

  dimensions = {
    QueueName = var.sqs_queue_names[0]
  }

  tags = var.common_tags
}

# ---------- Error Rate Alarm ----------

resource "aws_cloudwatch_metric_alarm" "error_rate" {
  alarm_name          = "${var.name_prefix}-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 20
  alarm_description   = "Model error rate exceeds 20%"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_name = "model_call_failure"
  namespace   = "whitespace"
  statistic   = "Average"
  period      = 300

  tags = var.common_tags
}

# ---------- AWS Budget ----------

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = var.budget_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = var.budget_notification_email != "" ? [var.budget_notification_email] : []
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = var.budget_notification_email != "" ? [var.budget_notification_email] : []
  }
}

# ---------- Dashboard ----------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.name_prefix}-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Model Call Latency"
          metrics = [["whitespace", "model_call_latency", { stat = "Average" }]]
          period  = 300
          region  = "sa-east-1"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title = "Model Errors"
          metrics = [
            ["whitespace", "model_call_failure", { stat = "Sum" }],
            ["whitespace", "model_call_success", { stat = "Sum" }],
          ]
          period = 300
          region = "sa-east-1"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "Estimated Cost (USD)"
          metrics = [["whitespace", "estimated_cost_usd", { stat = "Sum" }]]
          period  = 3600
          region  = "sa-east-1"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title = "SQS Queue Depth"
          metrics = [
            for qn in var.sqs_queue_names :
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", qn]
          ]
          period = 60
          region = "sa-east-1"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title = "Fargate Task Count"
          metrics = var.ecs_cluster_name != "" ? [
            ["AWS/ECS", "RunningTaskCount", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name]
          ] : []
          period = 60
          region = "sa-east-1"
        }
      },
    ]
  })
}
