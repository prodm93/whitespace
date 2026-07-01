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

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
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

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.fargate_security_group_id]
  }

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
