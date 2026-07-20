# Single orchestrate queue: the only queued job type after the rework.
# Ingest is presigned-URL (no queue); gap/ideation are stages inside an
# orchestrate job, not job types.
#
# Deletion candidates (verify producers before removing):
#   ingest, gap-council, ideation-council queues and their event-source
#   mappings in modules/lambda/main.tf (lines 225, 232, 302 in the
#   previous version).

locals {
  queues = ["orchestrate"]
}

# ---------- Dead-Letter Queue ----------

resource "aws_sqs_queue" "dlq" {
  for_each = toset(local.queues)

  name                      = "${var.name_prefix}-${each.value}-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-${each.value}-dlq"
  })
}

# ---------- Main Queue ----------

resource "aws_sqs_queue" "main" {
  for_each = toset(local.queues)

  name                       = "${var.name_prefix}-${each.value}"
  visibility_timeout_seconds = 900   # 15 min -- matches max dispatcher slice
  message_retention_seconds  = 86400 # 1 day
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.value].arn
    maxReceiveCount     = 3
  })

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-${each.value}"
  })
}
