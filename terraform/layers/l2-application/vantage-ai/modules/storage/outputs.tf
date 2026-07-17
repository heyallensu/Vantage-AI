output "document_bucket_name" { value = aws_s3_bucket.this["documents"].id }
output "document_bucket_arn" { value = aws_s3_bucket.this["documents"].arn }
output "frontend_bucket_name" { value = aws_s3_bucket.this["frontend"].id }
output "frontend_bucket_arn" { value = aws_s3_bucket.this["frontend"].arn }
output "frontend_bucket_regional_domain_name" {
  value = aws_s3_bucket.this["frontend"].bucket_regional_domain_name
}
