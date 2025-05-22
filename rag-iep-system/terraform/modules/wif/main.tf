variable "project_id" {}
variable "github_owner" {
  description = "GitHub organization or user that owns the repository"
  type        = string
  default     = "my-org"
}

resource "google_iam_workload_identity_pool" "pool" {
  provider = google-beta
  workload_identity_pool_id = "github-pool"
  display_name = "GitHub Actions Pool"
  project = var.project_id
}

resource "google_iam_workload_identity_pool_provider" "github" {
  provider = google-beta
  workload_identity_pool_id = google_iam_workload_identity_pool.pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name = "GitHub Provider"
  project = var.project_id

  attribute_condition = "assertion.repository_owner=='${var.github_owner}'"
  attribute_condition = "assertion.repository_owner=='example'"
  attribute_mapping = {
    "google.subject" = "assertion.sub"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

output "provider_name" {
  value = google_iam_workload_identity_pool_provider.github.name
}
