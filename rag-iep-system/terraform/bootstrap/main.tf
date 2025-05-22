variable "project_id" {}
variable "kms_key_id" {}

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

  encryption {
    default_kms_key_name = var.kms_key_id
  }
}
