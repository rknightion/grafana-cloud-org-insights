resource "aws_ecr_repository" "collector" {
  count = var.create_ecr_repository ? 1 : 0

  name                 = var.name_prefix
  image_tag_mutability = "MUTABLE"
  tags                 = local.tags

  image_scanning_configuration {
    # The image has no third-party Python packages at all, so the scan surface is the base image and the
    # AWS CLI. Cheap, and it is the only thing that would tell you the Debian base has gone stale.
    scan_on_push = true
  }
}

# Keep the last few images and let the rest go. A scheduled job only ever runs `:latest` or a pinned
# digest, so untagged predecessors accumulate for no reason.
resource "aws_ecr_lifecycle_policy" "collector" {
  count = var.create_ecr_repository ? 1 : 0

  repository = aws_ecr_repository.collector[0].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the 10 most recent tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "latest", "sha"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      },
    ]
  })
}
