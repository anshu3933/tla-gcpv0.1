# Service accounts with least privilege roles
locals {
  service_accounts = {
    "rag-infra-sa" = {
      display_name = "RAG Infrastructure Service Account"
      description  = "Service account for managing RAG system infrastructure via Terraform"
      roles = [
        # Project-level permissions needed for Terraform
        "roles/resourcemanager.projectIamAdmin",  # For managing IAM bindings
        "roles/serviceusage.serviceUsageAdmin",   # For enabling APIs
        "roles/billing.user",                     # For budget management
        
        # Service-specific permissions
        "roles/aiplatform.admin",                 # For managing Vertex AI resources
        "roles/run.admin",                        # For managing Cloud Run services
        "roles/storage.admin",                    # For managing storage buckets
        "roles/pubsub.admin",                     # For managing Pub/Sub resources
        "roles/firestore.admin",                  # For managing Firestore
        "roles/secretmanager.admin",              # For managing secrets
        "roles/redis.admin",                      # For managing Redis instance
        
        # Service account management
        "roles/iam.serviceAccountAdmin",          # For managing service accounts
        "roles/iam.serviceAccountUser"            # For impersonating service accounts
      ]
    }
    "rag-cicd-sa" = {
      display_name = "RAG CI/CD Service Account"
      description  = "Service account for CI/CD pipeline to deploy RAG services"
      roles = [
        # Container registry permissions
        "roles/artifactregistry.writer",          # For pushing container images
        
        # Cloud Run permissions - scoped to specific services
        "roles/run.developer",                    # For deploying to Cloud Run
        "roles/run.invoker",                      # For invoking Cloud Run services
        
        # Service account permissions - only for deployment
        "roles/iam.serviceAccountUser"            # For setting runtime service accounts
      ]
    }
    "rag-parser-sa" = {
      display_name = "Document Parser Service Account"
      description  = "Service account for document parsing service"
      roles = [
        "roles/pubsub.publisher",
        "roles/storage.objectViewer",
        "roles/storage.objectCreator"
      ]
    }
    "rag-embedder-sa" = {
      display_name = "Embedder Service Account"
      description  = "Service account for vector embedding service"
      roles = [
        "roles/storage.objectViewer",
        "roles/storage.objectAdmin",
        "roles/aiplatform.user"
      ]
    }
    "rag-api-sa" = {
      display_name = "RAG API Service Account"
      description  = "Service account for RAG API service"
      roles = [
        "roles/aiplatform.user",
        "roles/firestore.user",
        "roles/storage.objectViewer",
        "roles/secretmanager.secretAccessor"
      ]
    }
  }
}

resource "google_service_account" "service_accounts" {
  for_each = local.service_accounts
  
  account_id   = each.key
  display_name = each.value.display_name
  description  = each.value.description
  project      = var.project_id
}

# Grant roles to service accounts
resource "google_project_iam_member" "service_account_roles" {
  for_each = merge([
    for sa_name, sa_config in local.service_accounts : {
      for role in sa_config.roles : "${sa_name}-${role}" => {
        service_account = sa_name
        role           = role
      }
    }
  ]...)
  
  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.service_accounts[each.value.service_account].email}"
}

# Grant rag-infra-sa specific access to state bucket only
resource "google_storage_bucket_iam_member" "state_bucket_access" {
  bucket = "${var.project_id}-terraform-state"
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.service_accounts["rag-infra-sa"].email}"
}

resource "google_storage_bucket_iam_member" "state_bucket_write" {
  bucket = "${var.project_id}-terraform-state"
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.service_accounts["rag-infra-sa"].email}"
}

# Grant rag-cicd-sa specific access to Cloud Run services
resource "google_cloud_run_service_iam_member" "cicd_deployer" {
  for_each = toset(["doc-parser", "embedder", "rag-api"])
  
  location = google_cloud_run_service.rag_api.location
  project  = google_cloud_run_service.rag_api.project
  service  = each.key
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.service_accounts["rag-cicd-sa"].email}"
} 