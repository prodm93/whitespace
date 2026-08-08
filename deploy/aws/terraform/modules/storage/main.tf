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

# ---------- S3: LangGraph Checkpoint Overflow ----------

resource "aws_s3_bucket" "checkpoints" {
  bucket = "${var.name_prefix}-checkpoints"

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-checkpoints"
  })
}

resource "aws_s3_bucket_public_access_block" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  rule {
    id     = "expire-old-checkpoints"
    status = "Enabled"
    filter {}

    expiration {
      days = 7
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

# ---------- DynamoDB: LangGraph Checkpoints ----------

resource "aws_dynamodb_table" "checkpoints" {
  name         = "${var.name_prefix}-checkpoints"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-checkpoints"
  })
}
