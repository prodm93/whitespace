# ---------- DynamoDB: Upload Reservations ----------

resource "aws_dynamodb_table" "reservations" {
  name         = "${var.name_prefix}-reservations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "s3_key"

  attribute {
    name = "s3_key"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user_id-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-reservations"
  })
}

# ---------- DynamoDB: Sessions ----------

resource "aws_dynamodb_table" "sessions" {
  name         = "${var.name_prefix}-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-sessions"
  })
}
