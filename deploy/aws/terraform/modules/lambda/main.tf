# ---------- IAM Role (shared across all Lambdas) ----------

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "lambda" {
  name = "${var.name_prefix}-lambda"

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

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_s3" {
  name = "${var.name_prefix}-lambda-s3"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject"]
      Resource = "${var.results_bucket_arn}/*"
    }]
  })
}

# ---------- IAM Role (pipeline orchestrator — needs broader permissions) ----------

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
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage",
        ]
        Resource = "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.name_prefix}-*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = [
          "${var.results_bucket_arn}/*",
          "${var.checkpoints_bucket_arn}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
        ]
        Resource = "*"
      },
    ]
  })
}

# ---------- Authoriser ----------

resource "aws_lambda_function" "authoriser" {
  function_name = "${var.name_prefix}-authoriser"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 10
  memory_size   = 128

  filename         = "${var.lambda_build_dir}/authoriser.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/authoriser.zip")

  environment {
    variables = {
      CLERK_JWKS_URL = var.clerk_jwks_url
      CLERK_ISSUER   = var.clerk_issuer
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-authoriser"
  })
}

# ---------- Credential Validator ----------

resource "aws_lambda_function" "credential_validator" {
  function_name = "${var.name_prefix}-credential-validator"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = "${var.lambda_build_dir}/credential_validator.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/credential_validator.zip")

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-credential-validator"
  })
}

# ---------- Search Dispatcher ----------

resource "aws_lambda_function" "search_dispatcher" {
  function_name = "${var.name_prefix}-search-dispatcher"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 120
  memory_size   = 512

  filename         = "${var.lambda_build_dir}/search_dispatcher.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/search_dispatcher.zip")

  environment {
    variables = {
      RESULTS_BUCKET = var.results_bucket_name
      AWS_REGION     = var.aws_region
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-search-dispatcher"
  })
}

# ---------- Pipeline Orchestrator (container image) ----------

resource "aws_lambda_function" "pipeline_orchestrator" {
  function_name = "${var.name_prefix}-pipeline-orchestrator"
  role          = aws_iam_role.pipeline.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}:latest"
  timeout       = 900
  memory_size   = 2048

  environment {
    variables = {
      MODE                    = "saas"
      AWS_REGION              = var.aws_region
      RESULTS_BUCKET          = var.results_bucket_name
      CHECKPOINTS_TABLE       = var.checkpoints_table_name
      CHECKPOINTS_BUCKET      = var.checkpoints_bucket_name
      JOBS_TABLE              = var.jobs_table_name
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-pipeline-orchestrator"
  })
}

# ---------- SQS → Pipeline Orchestrator Trigger ----------

resource "aws_lambda_event_source_mapping" "sqs_ingest" {
  event_source_arn = var.ingest_queue_arn
  function_name    = aws_lambda_function.pipeline_orchestrator.arn
  batch_size       = 1
  enabled          = true
}

resource "aws_lambda_event_source_mapping" "sqs_gap_council" {
  event_source_arn = var.gap_council_queue_arn
  function_name    = aws_lambda_function.pipeline_orchestrator.arn
  batch_size       = 1
  enabled          = true
}

resource "aws_lambda_event_source_mapping" "sqs_ideation_council" {
  event_source_arn = var.ideation_council_queue_arn
  function_name    = aws_lambda_function.pipeline_orchestrator.arn
  batch_size       = 1
  enabled          = true
}
