resource "google_redis_instance" "cache" {
  name           = "rag-cache"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region
  
  redis_version = "REDIS_6_X"
  display_name  = "RAG Response Cache"
  
  auth_enabled = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"
} 