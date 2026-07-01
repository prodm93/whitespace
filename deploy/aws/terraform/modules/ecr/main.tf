resource "aws_ecr_repository" "backend" {
  name                 = "${var.name_prefix}-backend"
  # Immutable tags prevent image mutation attacks; CI pushes unique tags per build
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-backend"
  })
}

resource "aws_ecr_lifecycle_policy" "keep_last_5" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
