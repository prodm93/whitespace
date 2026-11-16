resource "aws_secretsmanager_secret" "pipeline" {
  name                    = "${var.name_prefix}-pipeline"
  recovery_window_in_days = var.recovery_window_in_days

  description = "Secrets of the pipeline function, as one JSON object. Required keys: neo4j_uri, neo4j_username, neo4j_password. Optional keys: exa_api_key, langsmith_api_key. Terraform creates the secret empty; put the value in with: aws secretsmanager put-secret-value --secret-id ${var.name_prefix}-pipeline --secret-string file://<a JSON file outside the repo>"

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-pipeline"
  })
}
