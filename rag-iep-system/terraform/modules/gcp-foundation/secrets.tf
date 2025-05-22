resource "google_secret_manager_secret" "secrets" {
  for_each = toset([
    "firebase-admin-key",
    "openai-api-key",  # If using OpenAI
    "oauth-client-id"
  ])
  
  secret_id = each.key
  project   = var.project_id
  
  replication {
    automatic = true
  }
}

# Grant access to rag-api-sa
resource "google_secret_manager_secret_iam_member" "api_access" {
  for_each = google_secret_manager_secret.secrets
  
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.service_accounts["rag-api-sa"].email}"
} 