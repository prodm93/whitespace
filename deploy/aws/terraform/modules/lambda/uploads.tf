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
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = var.usage_table_arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
        ]
        Resource = [
          var.reservations_table_arn,
          "${var.reservations_table_arn}/index/user_id-index",
        ]
      },
    ]
  })
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
      UPLOADS_BUCKET     = var.uploads_bucket_name
      USAGE_TABLE        = var.usage_table_name
      RESERVATIONS_TABLE = var.reservations_table_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-upload-url" })
}

# ---------- IAM Role (upload_confirm) ----------

resource "aws_iam_role" "upload_confirm" {
  name = "${var.name_prefix}-upload-confirm-role"

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

resource "aws_iam_role_policy_attachment" "upload_confirm_basic" {
  role       = aws_iam_role.upload_confirm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "upload_confirm_permissions" {
  name = "${var.name_prefix}-upload-confirm-perms"
  role = aws_iam_role.upload_confirm.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
        ]
        Resource = var.reservations_table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = var.usage_table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:DeleteObject"]
        Resource = "${var.uploads_bucket_arn}/uploads/*"
      },
    ]
  })
}

# ---------- Upload Confirm ----------

resource "aws_lambda_function" "upload_confirm" {
  function_name = "${var.name_prefix}-upload-confirm"
  role          = aws_iam_role.upload_confirm.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 10
  memory_size   = 128

  filename         = "${var.lambda_build_dir}/upload_confirm.zip"
  source_code_hash = filebase64sha256("${var.lambda_build_dir}/upload_confirm.zip")

  environment {
    variables = {
      RESERVATIONS_TABLE = var.reservations_table_name
      USAGE_TABLE        = var.usage_table_name
      UPLOADS_BUCKET     = var.uploads_bucket_name
    }
  }

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-upload-confirm" })
}
