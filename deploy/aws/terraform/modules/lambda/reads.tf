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
