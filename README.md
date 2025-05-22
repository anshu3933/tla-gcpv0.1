# tla-gcpv0.1
gcp back end attempt 1

## Bootstrapping Terraform State

Before running `terraform init` in the main configuration, create the remote state bucket once:

```bash
cd terraform/bootstrap
terraform init
terraform apply -var="project_id=YOUR_PROJECT" -var="kms_key_id=YOUR_KMS_KEY"
```

This step only needs to run a single time.

## Development Workflow

Before committing changes run:

```bash
black .
pytest
terraform fmt -recursive
```

The Workload Identity Federation module expects the GitHub organization name via
`var.github_owner`. Set this variable when applying Terraform.

To protect data from exfiltration, the `vpcsc` module defines a Service
Perimeter. Include services like Storage, Firestore, Vertex AI and Secret
Manager in the `restricted_services` variable.

Build the Cloud Function source once and upload the zip file:

```bash
cd services
zip -r upsert-function.zip upsert-function
```
