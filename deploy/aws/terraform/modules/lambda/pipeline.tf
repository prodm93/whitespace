data "aws_caller_identity" "current" {}

# ---------- IAM Role (pipeline orchestrator) ----------

resource "aws_iam_role" "pipeline" {
  name = "${var.name_prefix}-pipeline"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "pipeline_basic" {
  role       = aws_iam_role.pipeline.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "pipeline_permissions" {
  name = "${var.name_prefix}-pipeline-perms"
  role = aws_iam_role.pipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = [
          "${var.results_bucket_arn}/*",
          "${var.checkpoints_bucket_arn}/*",
          # Uploads bucket: pipeline reads user documents at analysis time.
          "${var.uploads_bucket_arn}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:Query", "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-*"
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
      },
    ]
  })
}

# ---------- IAM Role (dispatcher) ----------

resource "aws_iam_role" "dispatcher" {
  name = "${var.name_prefix}-dispatcher-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "dispatcher_invoke" {
  name = "${var.name_prefix}-dispatcher-invoke"
  role = aws_iam_role.dispatcher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.pipeline_orchestrator.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = var.orchestrate_queue_arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "*"
      },
    ]
  })
}

# ---------- Pipeline Orchestrator (container image, durable function) ----------

resource "aws_lambda_function" "pipeline_orchestrator" {
  function_name = "${var.name_prefix}-pipeline-orchestrator"
  role          = aws_iam_role.pipeline.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}:latest"
  timeout       = 900
  memory_size   = 2048

  durable_config {
    execution_timeout        = 86400
    retention_period_in_days = 7
  }

  environment {
    variables = {
      MODE           = "saas"
      RESULTS_BUCKET = var.results_bucket_name
      UPLOADS_BUCKET = var.uploads_bucket_name
      JOBS_TABLE     = var.jobs_table_name
      SESSIONS_TABLE = var.sessions_table_name
      USAGE_TABLE    = var.usage_table_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-pipeline-orchestrator" })
}

# ---------- Durable Dispatcher ----------

resource "aws_lambda_function" "durable_dispatcher" {
  function_name = "${var.name_prefix}-durable-dispatcher"
  role          = aws_iam_role.dispatcher.arn
  runtime       = "python3.12"
  handler       = "handler.handler"
  filename      = "${path.module}/../../lambda_build/durable_dispatcher.zip"
  timeout       = 60
  memory_size   = 128

  environment {
    variables = {
      PIPELINE_FUNCTION = aws_lambda_function.pipeline_orchestrator.function_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-durable-dispatcher" })
}

# ---------- SQS -> Dispatcher (orchestrate queue only) ----------

resource "aws_lambda_event_source_mapping" "sqs_orchestrate" {
  event_source_arn = var.orchestrate_queue_arn
  function_name    = aws_lambda_function.durable_dispatcher.arn
  batch_size       = 1
  enabled          = true
}
