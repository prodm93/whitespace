locals {
  parameters = {
    clerk_secret_key     = var.clerk_secret_key
    stripe_secret_key    = var.stripe_secret_key
    clerk_webhook_secret = var.clerk_webhook_secret
    openrouter_api_key   = var.openrouter_api_key
    exa_api_key          = var.exa_api_key
    firecrawl_api_key    = var.firecrawl_api_key
    langsmith_api_key    = var.langsmith_api_key
  }
}

resource "aws_ssm_parameter" "secret" {
  for_each = local.parameters

  name  = "/${var.name_prefix}/${replace(each.key, "_", "-")}"
  type  = "SecureString"
  value = each.value != "" ? each.value : "placeholder"

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-${each.key}"
  })

  lifecycle {
    ignore_changes = [value]
  }
}
