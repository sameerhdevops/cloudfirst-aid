# CloudFirst Aid Architecture Diagrams

This directory contains editable [Mermaid](https://mermaid.js.org/) source files for the architecture, cloud infrastructure references, and troubleshooting workflows used in CloudFirst Aid.

GitHub natively renders Mermaid code blocks in Markdown. You can also view or edit these diagrams using the online [Mermaid Live Editor](https://mermaid.live).

---

## Diagram List

| Diagram | Source File | Description |
|---|---|---|
| **A. Project Architecture** | [`architecture.mmd`](architecture.mmd) | Component architecture, data flow from symptom to audit report |
| **B. Reference AWS Architecture** | [`aws_reference_architecture.mmd`](aws_reference_architecture.mmd) | Multi-tier AWS website architecture (ALB, EC2, RDS, VPC, S3) |
| **C. Incident Investigation Workflow** | [`incident_workflow.mmd`](incident_workflow.mmd) | Operational sequence from customer alert to post-incident review |
| **D. Troubleshooting Decision Tree** | [`troubleshooting_decision_flow.mmd`](troubleshooting_decision_flow.mmd) | Diagnostic branching logic for website connectivity failures |

---

## Rendering in Markdown

Below are embedded renderings of each diagram.

### Diagram A: Project Architecture

```mermaid
graph TD
    User["CLI User / Fresher Engineer"] -->|cloudfirst-aid list / show / triage / report| CLI["CLI Entrypoint (cli.py)"]

    subgraph CoreEngine["CloudFirst Aid Core Engine"]
        CLI --> CatalogLoader["Catalog Loader & Validator (catalog.py)"]
        CLI --> TriageEngine["Deterministic Triage Engine (triage.py)"]
        CLI --> ReportGen["Incident Report Generator (reports.py)"]
        CLI -.->|Explicit opt-in| AWSInspector["Read-Only AWS Inspector (aws_readonly.py)"]

        TriageEngine -->|Evaluates| Rules["Diagnostic Rules (Scenario-Specific)"]
        TriageEngine -->|Produces| Findings["Findings (Observed / Supported / Confirmed)"]
    end

    subgraph DataSources["Data Assets & Catalog"]
        CatalogLoader --> CatalogFiles["30 Structured Scenarios (scenarios/catalog/*.json)"]
        TriageEngine --> Fixtures["Evidence Fixtures (tests/fixtures/evidence_*.json)"]
        Operator["Engineer / Host Operator"] -.->|Runs manually on target host| LocalCollector["Standalone Diagnostic Utility (scripts/collect_linux_diagnostics.sh)"]
        AWSInspector -.->|Boto3 Read-Only Describe*| LiveAWS["AWS APIs (Live EC2/VPC Snapshot)"]
    end

    subgraph Outputs["Output Artifacts"]
        ReportGen --> MarkdownReport["Structured Incident Report (reports/*.md)"]
        CatalogFiles -.-> Runbooks["14 Detailed Field Runbooks (runbooks/*/*.md)"]
    end
```

---

### Diagram B: Reference AWS Website Architecture

> **Notice:** This is a reference architecture used to illustrate real-world troubleshooting scenarios. It does not require active cloud resources or incur AWS costs to use CloudFirst Aid.

```mermaid
graph TD
    Client["Web Browser / Client"] -->|HTTPS:443 / DNS Query| R53["Amazon Route 53 (DNS)"]
    R53 -.->|Resolves to| CF["Amazon CloudFront (CDN) / ACM TLS"]
    CF -->|Origin Traffic| IGW["Internet Gateway (VPC: 10.0.0.0/16)"]

    subgraph VPC["Amazon Virtual Private Cloud (10.0.0.0/16)"]
        IGW --> PublicSubnet["Public Subnet (10.0.1.0/24)"]
        
        subgraph PublicTier["Public Tier"]
            PublicSubnet --> ALB["Application Load Balancer (ALB SG)"]
            PublicSubnet --> NATGW["NAT Gateway (Elastic IP)"]
        end

        ALB -->|TCP:8080 Target Group Health Check| AppSubnet["Private App Subnet (10.0.2.0/24)"]

        subgraph PrivateTier["Private Application Tier"]
            AppSubnet --> EC2A["EC2 App Instance 1 (App SG)"]
            AppSubnet --> EC2B["EC2 App Instance 2 (App SG)"]
            EC2A -->|Egress to Internet via 0.0.0.0/0| NATGW
            EC2A -->|IAM Instance Profile| S3Endpoint["S3 Gateway VPC Endpoint"]
        end

        subgraph DatabaseTier["Isolated Database Tier"]
            EC2A -->|TCP:3306 DB SG| RDSPrimary["Amazon RDS MySQL Primary (Multi-AZ)"]
            RDSPrimary -.->|Synchronous Replication| RDSStandby["Amazon RDS Standby Replica"]
        end
    end

    S3Endpoint --> S3Bucket["Amazon S3 Bucket (App Assets & Backups)"]
    EC2A -.->|CloudWatch Agent| CW["Amazon CloudWatch (Metrics, Logs, Alarms)"]
```

---

### Diagram C: Incident Investigation Workflow

```mermaid
flowchart TD
    Start(["Customer Alert / Monitoring Alarm"]) --> Triage0["Initial Observation: Capture exact error string & timestamp"]
    Triage0 --> Scope["Establish Scope: 1 user, all users, or specific region?"]
    Scope --> Freeze{"Before Changing Anything:<br/>Do we have diagnostic baseline?"}
    
    Freeze -->|No| Collect["Collect Diagnostic Evidence:<br/>df -h, ss -tlnp, describe-security-groups, logs"]
    Freeze -->|Yes| Analyze["Evaluate Evidence Against Hypotheses"]

    Collect --> Analyze
    
    Analyze --> CheckSufficient{"Is evidence sufficient<br/>to confirm single root cause?"}
    
    CheckSufficient -->|Insufficient Evidence| BranchInvestigate["Branch: Needs Further Investigation<br/>Gather network traces, journalctl, or deeper logs"]
    BranchInvestigate --> Collect

    CheckSufficient -->|Confirmed Root Cause| RemediationPlan["Formulate Safe Remediation Plan<br/>(Prefer non-destructive, reversible steps)"]
    
    RemediationPlan --> Execute["Apply Fix (e.g. update SG rule, truncate runaway log)"]
    Execute --> Verification["Verification: Did fix resolve symptom without regressions?"]
    
    Verification --> Success{"Verification Passed?"}
    Success -->|No| Rollback["Rollback to safe state & re-evaluate"]
    Rollback --> Analyze
    
    Success -->|Yes| Report["Document: Generate Incident Report & Audit Trail"]
    Report --> Prevention["Prevention: Update CloudWatch alarms, runbooks, or IaC"]
    Prevention --> Done(["Incident Closed"])
```

---

### Diagram D: Troubleshooting Decision Tree (Website Unreachable)

```mermaid
flowchart TD
    Start(["Website Unreachable / Error"]) --> CheckType{"What is the exact HTTP response or symptom?"}

    CheckType -->|Connection Timed Out| CheckNet{"Can client complete TCP handshake to port 80/443?"}
    CheckNet -->|No| SG["Check Security Group: Is port 80/443 open to client CIDR?"]
    CheckNet -->|Yes| Route["Check Subnet Route Table: Is 0.0.0.0/0 routed to IGW?"]

    CheckType -->|Connection Refused| Refused{"Is web server process active & listening?"}
    Refused -->|Process Dead| StartSvc["Run: systemctl status nginx / gunicorn<br/>Inspect journalctl -u for crash trace"]
    Refused -->|Listening on 127.0.0.1| BindFix["Process bound to localhost loopback!<br/>Rebind application to 0.0.0.0"]

    CheckType -->|HTTP 502 Bad Gateway| FiveZeroTwo{"ALB or Reverse Proxy cannot reach upstream backend"}
    FiveZeroTwo --> UpstreamCheck["1. Check backend daemon status<br/>2. Verify target SG allows proxy SG<br/>3. Check ALB target health: describe-target-health"]

    CheckType -->|HTTP 504 Gateway Timeout| FiveZeroFour{"Backend is running but too slow"}
    FiveZeroFour --> TimeoutCheck["1. Check RDS slow query logs & DB CPU<br/>2. Inspect top / free for high load average<br/>3. Verify backend keepalive > ALB timeout"]

    CheckType -->|HTTP 403 Forbidden| FourZeroThree{"Web server permissions issue"}
    FourZeroThree --> PermCheck["1. Verify file owner matching web server user<br/>2. Ensure directory has execute +x bit<br/>3. Check S3 bucket policy if S3-hosted"]
```
