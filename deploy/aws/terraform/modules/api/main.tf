# ---------- API Gateway HTTP API ----------

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 3600
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-api"
  })
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.name_prefix}-api"
  retention_in_days = 14

  tags = var.common_tags
}

# ---------- Clerk JWT Authoriser ----------

resource "aws_apigatewayv2_authorizer" "clerk" {
  count = var.clerk_authoriser_lambda_invoke_arn != "" ? 1 : 0

  api_id                            = aws_apigatewayv2_api.main.id
  name                              = "${var.name_prefix}-clerk-auth"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = var.clerk_authoriser_lambda_invoke_arn
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  identity_sources                  = ["$request.header.Authorization"]
}

resource "aws_lambda_permission" "api_authoriser" {
  count = var.clerk_authoriser_lambda_function_arn != "" ? 1 : 0

  statement_id  = "AllowAPIGatewayAuthoriser"
  action        = "lambda:InvokeFunction"
  function_name = var.clerk_authoriser_lambda_function_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ---------- Lambda Integrations ----------

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = var.lambda_invoke_arns

  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "lambda" {
  for_each = var.lambda_invoke_arns

  api_id    = aws_apigatewayv2_api.main.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.key].id}"

  authorization_type = length(aws_apigatewayv2_authorizer.clerk) > 0 && contains(var.authenticated_routes, each.key) ? "CUSTOM" : "NONE"
  authorizer_id      = length(aws_apigatewayv2_authorizer.clerk) > 0 && contains(var.authenticated_routes, each.key) ? aws_apigatewayv2_authorizer.clerk[0].id : null
}

resource "aws_lambda_permission" "api_lambda" {
  for_each = var.lambda_function_arns

  statement_id  = "AllowAPIGateway-${replace(each.key, "/[^a-zA-Z0-9_-]/", "-")}"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
