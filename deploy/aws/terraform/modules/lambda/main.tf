# ---------- IAM Role (shared: authoriser, credential validator, search dispatcher) ----------

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

# ---------- IAM Role (orchestrate_enqueue) ----------

resource "aws_iam_role" "enqueue" {
  name = "${var.name_prefix}-enqueue-role"

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

resource "aws_iam_role_policy_attachment" "enqueue_basic" {
  role       = aws_iam_role.enqueue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "enqueue_permissions" {
  name = "${var.name_prefix}-enqueue-perms"
  role = aws_iam_role.enqueue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = var.orchestrate_queue_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = var.jobs_table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = var.usage_table_arn
      },
    ]
  })
}

# ---------- IAM Role (upload_url) ----------

resource "aws_iam_role" "upload_url" {
  name = "${var.name_prefix}-upload-url-role"

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

resource "aws_iam_role_policy_attachment" "upload_url_basic" {
  role       = aws_iam_role.upload_url.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "upload_url_permissions" {
  name = "${var.name_prefix}-upload-url-perms"
  role = aws_iam_role.upload_url.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${var.uploads_bucket_arn}/uploads/*"
      },
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = var.uploads_bucket_arn
        Condition = { StringLike = { "s3:prefix" = ["uploads/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = var.usage_table_arn
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

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-authoriser" })
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

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-credential-validator" })
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
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-search-dispatcher" })
}

# ---------- Orchestrate Enqueue ----------

resource "aws_lambda_function" "orchestrate_enqueue" {
  function_name = "${var.name_prefix}-orchestrate-enqueue"
  role          = aws_iam_role.enqueue.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 10
  memory_size   = 128

  filename         = "${var.lambda_build_dir}/orchestrate_enqueue.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/orchestrate_enqueue.zip")

  environment {
    variables = {
      JOBS_TABLE            = var.jobs_table_name
      ORCHESTRATE_QUEUE_URL = var.orchestrate_queue_url
      USAGE_TABLE           = var.usage_table_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-orchestrate-enqueue" })
}

# ---------- Upload URL ----------

resource "aws_lambda_function" "upload_url" {
  function_name = "${var.name_prefix}-upload-url"
  role          = aws_iam_role.upload_url.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 10
  memory_size   = 128

  filename         = "${var.lambda_build_dir}/upload_url.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/upload_url.zip")

  environment {
    variables = {
      UPLOADS_BUCKET = var.uploads_bucket_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-upload-url" })
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

# ---------- IAM Role (runs_reader) ----------

resource "aws_iam_role" "runs_reader" {
  name = "${var.name_prefix}-runs-reader-role"

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

resource "aws_iam_role_policy_attachment" "runs_reader_basic" {
  role       = aws_iam_role.runs_reader.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "runs_reader_permissions" {
  name = "${var.name_prefix}-runs-reader-perms"
  role = aws_iam_role.runs_reader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = var.jobs_table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = var.sessions_table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.results_bucket_arn}/results/*"
      },
    ]
  })
}

# ---------- Runs Reader ----------

resource "aws_lambda_function" "runs_reader" {
  function_name = "${var.name_prefix}-runs-reader"
  role          = aws_iam_role.runs_reader.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = "${var.lambda_build_dir}/runs_reader.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/runs_reader.zip")

  environment {
    variables = {
      JOBS_TABLE     = var.jobs_table_name
      SESSIONS_TABLE = var.sessions_table_name
      RESULTS_BUCKET = var.results_bucket_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-runs-reader" })
}
