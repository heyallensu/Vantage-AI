variable "name_prefix" {
  type = string
}

variable "dlq_name" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "alarm_actions" {
  type = list(string)
}

variable "lambda_error_threshold" {
  type = number
}

variable "dlq_visible_messages_threshold" {
  type = number
}