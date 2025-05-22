variable "project_id" {}
variable "perimeter_name" { default = "rag-perimeter" }
variable "restricted_services" { type = list(string) }

resource "google_access_context_manager_service_perimeter" "perimeter" {
  name        = "accessPolicies/${var.project_id}/servicePerimeters/${var.perimeter_name}"
  parent      = "accessPolicies/${var.project_id}"
  title       = var.perimeter_name
  status {
    restricted_services = var.restricted_services
  }
}
