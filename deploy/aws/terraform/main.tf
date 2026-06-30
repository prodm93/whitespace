locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ---------- Monitoring (first — other modules reference log groups) ----------

module "monitoring" {
  source = "./modules/monitoring"

  name_prefix               = local.name_prefix
  common_tags               = local.common_tags
  budget_limit_usd          = var.budget_limit_usd
  budget_notification_email = var.budget_notification_email
  sqs_queue_names = [
    module.queue.ingest_queue_name,
  ]
  ecs_cluster_name = "${local.name_prefix}-cluster"
  ecs_service_name = "${local.name_prefix}-backend"
}

# ---------- Networking ----------

module "networking" {
  source = "./modules/networking"

  name_prefix    = local.name_prefix
  common_tags    = local.common_tags
  vpc_cidr       = var.vpc_cidr
  az_count       = var.az_count
  container_port = var.container_port
}

# ---------- ECR ----------

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
  common_tags = local.common_tags
}

# ---------- Queue ----------

module "queue" {
  source = "./modules/queue"

  name_prefix = local.name_prefix
  common_tags = local.common_tags
}

# ---------- Secrets ----------

module "secrets" {
  source = "./modules/secrets"

  name_prefix          = local.name_prefix
  common_tags          = local.common_tags
  clerk_secret_key     = var.clerk_secret_key
  stripe_secret_key    = var.stripe_secret_key
  clerk_webhook_secret = var.clerk_webhook_secret
  openrouter_api_key   = var.openrouter_api_key
  exa_api_key          = var.exa_api_key
  firecrawl_api_key    = var.firecrawl_api_key
  langsmith_api_key    = var.langsmith_api_key
}

# ---------- Storage ----------

module "storage" {
  source = "./modules/storage"

  name_prefix = local.name_prefix
  common_tags = local.common_tags
}

# ---------- Compute ----------

module "compute" {
  source = "./modules/compute"

  name_prefix               = local.name_prefix
  common_tags               = local.common_tags
  vpc_id                    = module.networking.vpc_id
  private_subnet_ids        = module.networking.private_subnet_ids
  public_subnet_ids         = module.networking.public_subnet_ids
  fargate_security_group_id = module.networking.fargate_security_group_id
  ecr_repository_url        = module.ecr.repository_url
  container_port            = var.container_port
  cpu                       = var.fargate_cpu
  memory                    = var.fargate_memory
  min_capacity              = var.fargate_min_capacity
  max_capacity              = var.fargate_max_capacity
  scale_down_cron           = var.scale_down_cron
  scale_up_cron             = var.scale_up_cron
  sqs_queue_name            = module.queue.ingest_queue_name
  aws_region                = var.aws_region
  ssm_parameter_arns        = module.secrets.parameter_arns
  log_group_name            = module.monitoring.fargate_log_group_name
}

# ---------- Lambda ----------

module "lambda" {
  source = "./modules/lambda"

  name_prefix               = local.name_prefix
  common_tags               = local.common_tags
  lambda_build_dir          = "${path.module}/../lambda_build"
  vpc_id                    = module.networking.vpc_id
  private_subnet_ids        = module.networking.private_subnet_ids
  fargate_security_group_id = module.networking.fargate_security_group_id
  results_bucket_name       = module.storage.results_bucket_name
  results_bucket_arn        = module.storage.results_bucket_arn
  log_group_name            = module.monitoring.lambda_log_group_name
  aws_region                = var.aws_region
}

# ---------- API Gateway ----------

module "api" {
  source = "./modules/api"

  name_prefix        = local.name_prefix
  common_tags        = local.common_tags
  vpc_id             = module.networking.vpc_id
  nlb_arn            = module.compute.nlb_arn
  nlb_listener_arn   = module.compute.nlb_listener_arn
  container_port     = var.container_port
  private_subnet_ids = module.networking.private_subnet_ids

  clerk_authoriser_lambda_invoke_arn   = module.lambda.authoriser_invoke_arn
  clerk_authoriser_lambda_function_arn = module.lambda.authoriser_function_arn

  lambda_invoke_arns = {
    "POST /api/credentials/validate" = module.lambda.credential_validator_invoke_arn
    "POST /api/search"               = module.lambda.search_dispatcher_invoke_arn
  }
  lambda_function_arns = {
    "POST /api/credentials/validate" = module.lambda.credential_validator_function_arn
    "POST /api/search"               = module.lambda.search_dispatcher_function_arn
  }
}

# ---------- CDN ----------

module "cdn" {
  source = "./modules/cdn"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix          = local.name_prefix
  common_tags          = local.common_tags
  use_custom_domain    = var.use_custom_domain
  domain_name          = var.domain_name
  hosted_zone_id       = var.hosted_zone_id
  api_gateway_endpoint = module.api.api_endpoint
}
