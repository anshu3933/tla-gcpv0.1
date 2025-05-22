variable "project_id" {}
variable "location" {}

resource "google_compute_security_policy" "waf" {
  name        = "rag-api-waf"
  description = "WAF for RAG API"

  rule {
    priority = 100
    match {
      expr {
        expression = "request.path.matches('/(healthz|readyz)')"
      }
    }
    action = "allow"
  }

  rule {
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    action = "allow"
    rate_limit_options {
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
      conform_action = "allow"
      exceed_action  = "deny(429)"
    }
  }

  rule {
    priority = 2000
    match {
      expr {
        expression = "!(origin.region_code == 'US')"
      }
    }
    action = "deny(403)"
  }
}

output "policy_name" {
  value = google_compute_security_policy.waf.name
}
