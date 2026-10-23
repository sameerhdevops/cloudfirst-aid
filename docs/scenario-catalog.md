# CloudFirst Aid — Scenario Catalog Matrix

This document provides a comprehensive mapping of all **30 incident scenarios** in the CloudFirst Aid troubleshooting catalog, including their operational category, difficulty, severity, availability of detailed field runbooks, and availability of reproducible demo fixtures.

---

## Catalog Overview

- **Total Scenarios:** 30
- **Categories:** 6 (`ec2`, `linux`, `networking`, `application`, `iam-s3`, `monitoring`)
- **Detailed Runbooks:** 14
- **Reproducible Demos:** 6

---

## Scenario Matrix

| ID | Title | Category | Severity | Difficulty | Runbook | Demo Fixture |
|---|---|---|---|---|:---:|:---:|
| **CFA-001** | EC2 SSH Connection Times Out | `ec2` | `HIGH` | Beginner | [View](../runbooks/ec2/CFA-001_ssh_connection_timeout.md) | `tests/fixtures/evidence_CFA-001.json` |
| **CFA-002** | SSH Returns Permission Denied (publickey) | `ec2` | `HIGH` | Beginner | [View](../runbooks/ec2/CFA-002_ssh_permission_denied.md) | - |
| **CFA-003** | EC2 Instance Fails Status Check (1/2 or 0/2) | `ec2` | `CRITICAL` | Intermediate | [View](../runbooks/ec2/CFA-003_ec2_status_checks.md) | - |
| **CFA-004** | EC2 Running but Application Unreachable | `ec2` | `HIGH` | Beginner | - | - |
| **CFA-005** | EC2 Outbound Internet Access Fails | `ec2` | `HIGH` | Intermediate | - | - |
| **CFA-006** | EC2 Instance Unable to Access S3 | `iam-s3` | `HIGH` | Intermediate | [View](../runbooks/aws-services/CFA-006_ec2_s3_instance_profile.md) | - |
| **CFA-007** | Website Returns HTTP 403 Forbidden or 404 Not Found | `application` | `MEDIUM` | Beginner | - | - |
| **CFA-008** | Website Returns HTTP 502 Bad Gateway | `application` | `CRITICAL` | Intermediate | [View](../runbooks/aws-services/CFA-008_website_502_bad_gateway.md) | - |
| **CFA-009** | Website Returns HTTP 504 Gateway Timeout | `application` | `HIGH` | Intermediate | - | - |
| **CFA-010** | Linux Root Filesystem 100% Full | `linux` | `CRITICAL` | Beginner | [View](../runbooks/linux/CFA-010_linux_disk_full.md) | `tests/fixtures/evidence_CFA-010.json` |
| **CFA-011** | Linux Inode Exhaustion (0 Inodes Available) | `linux` | `CRITICAL` | Intermediate | [View](../runbooks/linux/CFA-011_linux_inode_exhaustion.md) | `tests/fixtures/evidence_CFA-011.json` |
| **CFA-012** | High CPU or Memory Usage / OOM-Killer Triggered | `linux` | `HIGH` | Intermediate | [View](../runbooks/linux/CFA-012_high_cpu_memory_oom.md) | - |
| **CFA-013** | systemd Service Fails to Start (CrashLoop) | `linux` | `HIGH` | Intermediate | [View](../runbooks/linux/CFA-013_systemd_service_failure.md) | `tests/fixtures/evidence_CFA-013.json` |
| **CFA-014** | Linux File Permission Denied and POSIX ACL Mask Issue | `linux` | `MEDIUM` | Intermediate | - | - |
| **CFA-015** | Process Cannot Bind to Port (EADDRINUSE) | `linux` | `MEDIUM` | Beginner | - | - |
| **CFA-016** | EBS Volume Expanded but Linux Filesystem Not Resized | `linux` | `MEDIUM` | Intermediate | - | - |
| **CFA-017** | Application Load Balancer Reports Unhealthy Targets | `networking` | `CRITICAL` | Intermediate | [View](../runbooks/networking/CFA-017_alb_unhealthy_targets.md) | `tests/fixtures/evidence_CFA-017.json` |
| **CFA-018** | Private Subnet Instance Cannot Access Internet via NAT Gateway | `networking` | `HIGH` | Intermediate | [View](../runbooks/networking/CFA-018_private_subnet_nat_gateway.md) | - |
| **CFA-019** | VPC DNS Resolution Failure | `networking` | `HIGH` | Intermediate | [View](../runbooks/networking/CFA-019_vpc_dns_resolution.md) | - |
| **CFA-020** | S3 AccessDenied 403 / Bucket Policy Explicit Deny | `iam-s3` | `HIGH` | Intermediate | [View](../runbooks/aws-services/CFA-020_s3_bucket_policy_access_denied.md) | `tests/fixtures/evidence_CFA-020.json` |
| **CFA-021** | AWS CLI Using Wrong Account, Profile, or Region | `iam-s3` | `MEDIUM` | Beginner | - | - |
| **CFA-022** | S3 KMS-Encrypted Object AccessDenied | `iam-s3` | `HIGH` | Intermediate | - | - |
| **CFA-023** | CloudWatch Alarm Does Not Trigger Action | `monitoring` | `MEDIUM` | Intermediate | - | - |
| **CFA-024** | Application Cannot Connect to RDS Database | `monitoring` | `CRITICAL` | Intermediate | [View](../runbooks/aws-services/CFA-024_rds_connectivity_timeout.md) | - |
| **CFA-025** | Two EC2 Instances in Same VPC Cannot Communicate | `networking` | `HIGH` | Beginner | - | - |
| **CFA-026** | Public Subnet Instance Unreachable (Missing Public IP) | `networking` | `MEDIUM` | Beginner | - | - |
| **CFA-027** | Application Fails After EC2 Instance Reboot | `linux` | `HIGH` | Beginner | - | - |
| **CFA-028** | HTTPS / TLS Certificate Failure on Custom Domain | `application` | `HIGH` | Intermediate | - | - |
| **CFA-029** | Route 53 DNS Resolution Returns Stale IP | `networking` | `MEDIUM` | Intermediate | - | - |
| **CFA-030** | CloudWatch Agent Missing Memory and Disk Metrics | `monitoring` | `MEDIUM` | Intermediate | - | - |

---

## Categorization Breakdown

### 1. EC2 & SSH (CFA-001 to CFA-005)
Focuses on virtual machine lifecycle, hypervisor status checks (System vs. Instance), SSH key authentication, OpenSSH configuration, and fundamental host reachability.

### 2. Linux Systems Administration (CFA-010 to CFA-016, CFA-027)
Focuses on block storage versus inode capacity, unrotated log files, open deleted file handles, kernel OOM-killer actions, systemd service lifecycle, POSIX ACL masks, port binding conflicts, and partition expansion (`growpart`, `resize2fs`, `xfs_growfs`).

### 3. VPC & Cloud Networking (CFA-017 to CFA-019, CFA-025, CFA-026, CFA-029)
Covers Application Load Balancer target group health checks, NAT Gateway placement (public vs. private subnets), VPC DNS resolution (`enableDnsSupport`), Security Group stateful evaluation vs. stateless Network ACLs, and Route 53 TTL propagation.

### 4. IAM, S3, & Security (CFA-006, CFA-020 to CFA-022)
Deep dive into IAM policy evaluation logic: the precedence of explicit Deny statements in S3 bucket policies, EC2 IAM Instance Profiles, IMDSv2 token retrieval, credential precedence order in the AWS CLI, and AWS KMS key policies (`kms:Decrypt`).

### 5. Application & Web Services (CFA-007 to CFA-009, CFA-028)
Investigates Nginx reverse proxies, upstream socket communication, HTTP 502 Bad Gateway vs. HTTP 504 Gateway Timeout, document root filesystem permissions (HTTP 403), and ACM TLS/SSL certificate domain validation.

### 6. Monitoring & Cloud Databases (CFA-023, CFA-024, CFA-030)
Covers RDS database security group ingress referencing, CloudWatch alarm state transitions (`OK` -> `ALARM`), and CloudWatch Agent custom metrics collection.
