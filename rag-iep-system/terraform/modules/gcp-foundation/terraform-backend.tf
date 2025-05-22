resource "google_storage_bucket" "terraform_state" {
  name     = "${var.project_id}-terraform-state"
  location = "US"
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }
  
  uniform_bucket_level_access = true
} 