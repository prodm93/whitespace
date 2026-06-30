# ---------- S3: Uploads ----------

resource "aws_s3_bucket" "uploads" {
  bucket = "${var.name_prefix}-uploads"

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-uploads"
  })
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "expire-old-uploads"
    status = "Enabled"
    filter {}

    expiration {
      days = 90
    }
  }
}

# ---------- S3: Job Results ----------

resource "aws_s3_bucket" "results" {
  bucket = "${var.name_prefix}-job-results"

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-job-results"
  })
}

resource "aws_s3_bucket_public_access_block" "results" {
  bucket = aws_s3_bucket.results.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "results" {
  bucket = aws_s3_bucket.results.id

  rule {
    id     = "expire-old-results"
    status = "Enabled"
    filter {}

    expiration {
      days = 30
    }
  }
}

# ---------- DynamoDB: Usage Tracking ----------

resource "aws_dynamodb_table" "usage" {
  name         = "${var.name_prefix}-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-usage"
  })
}

# ---------- DynamoDB: Jobs ----------

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.name_prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-jobs"
  })
}
