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

resource "google_monitoring_alert_policy" "error_ratio" {
  display_name = "High 5xx error ratio"
  combiner     = "OR"
  notification_channels = []

  conditions {
    display_name = "5xx ratio >5%"
    condition_monitoring_query_language {
      query = <<-EOT
        fetch cloud_run_revision
        | metric 'run.googleapis.com/request_count'
        | align rate(1m)
        | group_by [], ratio(sum(val{response_code>=500}), sum(val))
        | condition val > 0.05
      EOT
      duration = '300s'
    }
  }
}
