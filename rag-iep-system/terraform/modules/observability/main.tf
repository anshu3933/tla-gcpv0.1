variable "project_id" {}

resource "google_logging_metric" "vertex_cost" {
  name   = "vertex_cost_micro_usd"
  filter = "jsonPayload.vertex_cost_micro_usd>0"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    display_name = "Vertex Cost Micro USD"
  }
}
