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
