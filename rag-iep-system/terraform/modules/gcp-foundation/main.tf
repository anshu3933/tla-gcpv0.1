variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "billing_account" {
  description = "Billing account ID"
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget amount in USD"
  type        = number
  default     = 1000
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "iamcredentials.googleapis.com",
    "secretmanager.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com"
  ])
  
  project = var.project_id
  service = each.key
  
  disable_on_destroy = false
}

# Budget alerts
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "Monthly RAG System Budget"
  
  budget_filter {
    projects = ["projects/${var.project_id}"]
  }
  
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount)
    }
  }
  
  threshold_rules {
    threshold_percent = 0.8
  }
  
  threshold_rules {
    threshold_percent = 0.95
  }
  
  threshold_rules {
    threshold_percent = 1.0
  }
} 