resource "google_cloud_run_service" "rag_api" {
  name     = "rag-api"
  location = var.region
  
  template {
    spec {
      service_account_name = "rag-api-sa@${var.project_id}.iam.gserviceaccount.com"
      
      containers {
        image = "gcr.io/${var.project_id}/rag-api:latest"
        
        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
        
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
      }
    }
    
    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "1"
        "autoscaling.knative.dev/maxScale" = "10"
        "run.googleapis.com/cpu-boost"      = "true"
      }
    }
  }
  
  traffic {
    percent         = 100
    latest_revision = true
  }
}

resource "google_cloud_run_service_iam_member" "noauth" {
  location = google_cloud_run_service.rag_api.location
  project  = google_cloud_run_service.rag_api.project
  service  = google_cloud_run_service.rag_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
  
  # This creates --no-allow-unauthenticated by NOT adding allUsers
  count = 0
} 