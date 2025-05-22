variable "project_id" {}
variable "location" {}

# Vector Search Index
resource "google_vertex_ai_index" "rag_index" {
  region       = var.location
  display_name = "rag-document-index"
  description  = "Index for RAG document chunks"
  
  metadata {
    # This is for initial data load only
    # Subsequent updates will be handled by the scheduled upsert script
    contents_delta_uri = "gs://${var.project_id}-vector-upserts/initial"
    
    config {
      dimensions                  = 768  # For textembedding-004
      approximate_neighbors_count = 100
      
      algorithm_config {
        tree_ah_config {
          leaf_node_embedding_count    = 1000
          leaf_nodes_to_search_percent = 10
        }
      }
    }
  }
  
  # Using STREAM_UPDATE to allow manual batch updates via the upsert script
  # This gives us more control over when updates happen and allows for
  # better monitoring and error handling of the update process
  index_update_method = "STREAM_UPDATE"
}

# Index Endpoint
resource "google_vertex_ai_index_endpoint" "rag_endpoint" {
  display_name = "rag-index-endpoint"
  description  = "Endpoint for RAG vector search"
  region       = var.location
  
  network = "projects/${var.project_id}/global/networks/default"
}

# Deploy index to endpoint
resource "google_vertex_ai_index_endpoint_deployed_index" "deployment" {
  index_endpoint = google_vertex_ai_index_endpoint.rag_endpoint.id
  index          = google_vertex_ai_index.rag_index.id
  deployed_index_id = "rag_index_deployed"
  
  display_name = "RAG Index Deployment"
  
  enable_access_logging = true
  
  automatic_resources {
    min_replica_count = 1
    max_replica_count = 3
  }
} 