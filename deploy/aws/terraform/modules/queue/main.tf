locals {
  queues = ["ingest", "gap-council", "ideation-council"]
}

# ---------- Dead-Letter Queues ----------

resource "aws_sqs_queue" "dlq" {
  for_each = toset(local.queues)

  name                      = "${var.name_prefix}-${each.value}-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-${each.value}-dlq"
  })
}

# ---------- Main Queues ----------

resource "aws_sqs_queue" "main" {
  for_each = toset(local.queues)

  name                       = "${var.name_prefix}-${each.value}"
  visibility_timeout_seconds = 900   # 15 min — matches max pipeline runtime
  message_retention_seconds  = 86400 # 1 day

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.value].arn
    maxReceiveCount     = 3
  })

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-${each.value}"
  })
}
