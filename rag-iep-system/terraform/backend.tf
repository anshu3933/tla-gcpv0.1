terraform {
  backend "gcs" {
    bucket = "${var.project_id}-terraform-state"
    prefix = "rag-system"
  }
}
