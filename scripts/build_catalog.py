"""Build and write the 30 scenario JSON files for CloudFirst Aid."""

from __future__ import annotations

import json
from pathlib import Path

CATALOG_DIR = Path("D:/Projects/cloudfirst-aid/scenarios/catalog")
CATALOG_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS = [
    {
        "id": "CFA-001",
        "title": "EC2 SSH Connection Times Out",
        "category": "ec2",
        "difficulty": "beginner",
        "severity": "high",
        "symptom": "Engineer attempts to connect to an Amazon EC2 instance via SSH (`ssh -i key.pem ec2-user@203.0.113.10`) and receives: 'ssh: connect to host 203.0.113.10 port 22: Connection timed out'.",
        "initial_observations": [
            "SSH client hangs for approximately 30-60 seconds before printing 'Connection timed out'.",
            "The instance shows 'running' state in the AWS Management Console.",
            "No TCP handshake is completed."
        ],
        "environment": "Amazon Linux 2 / 2023 EC2 instance in a public subnet with an attached Elastic IP.",
        "has_runbook": True,
        "has_demo": True,
        "tags": ["ssh", "ec2", "security-groups", "vpc", "nacl"],
        "possible_causes": [
            {
                "cause": "Security Group does not permit inbound TCP port 22 from the engineer's public IP",
                "likelihood": "common",
                "evidence_needed": "ec2:DescribeSecurityGroups showing no rule for port 22 or CIDR mismatch.",
                "remediation": "Add an inbound rule to the instance's Security Group authorizing TCP port 22 from your specific IP/32."
            },
            {
                "cause": "Subnet Route Table missing route to Internet Gateway (0.0.0.0/0 -> igw-xxx)",
                "likelihood": "common",
                "evidence_needed": "ec2:DescribeRouteTables showing no default 0.0.0.0/0 route to an attached IGW.",
                "remediation": "Attach an Internet Gateway to the VPC and add route 0.0.0.0/0 pointing to the IGW ID."
            },
            {
                "cause": "Network ACL (NACL) blocking inbound port 22 or outbound ephemeral ports (1024-65535)",
                "likelihood": "occasional",
                "evidence_needed": "ec2:DescribeNetworkAcls showing a Deny rule before Allow or missing outbound return rule.",
                "remediation": "Update subnet NACL to allow inbound port 22 and outbound ephemeral ports (1024-65535)."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Verify Instance State and Public IP Assignment",
                "command": "aws ec2 describe-instances --instance-ids i-0123456789abcdef0 --query 'Reservations[*].Instances[*].[State.Name,PublicIpAddress,SecurityGroups]' --output table",
                "explanation": "Confirm instance is running and has a public IPv4 address assigned.",
                "what_to_look_for": "State 'running' and non-empty PublicIpAddress."
            },
            {
                "order": 2,
                "title": "Inspect Inbound Security Group Rules for Port 22",
                "command": "aws ec2 describe-security-groups --group-ids sg-0123456789abcdef0 --query 'SecurityGroups[*].IpPermissions[?ToPort==`22`]' --output json",
                "explanation": "Verify an ingress rule exists allowing TCP port 22 from your current public IP.",
                "what_to_look_for": "Check IpRanges CIDR against your public IP (obtained via 'curl https://checkip.amazonaws.com')."
            },
            {
                "order": 3,
                "title": "Check Subnet Route Table for Internet Gateway Route",
                "command": "aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 --query 'RouteTables[*].Routes' --output table",
                "explanation": "A public subnet must have a 0.0.0.0/0 route target matching igw-xxxxxxxx.",
                "what_to_look_for": "DestinationCidrBlock 0.0.0.0/0 with GatewayId starting with igw-."
            },
            {
                "order": 4,
                "title": "Inspect Subnet Network ACL Rules (Inbound and Outbound)",
                "command": "aws ec2 describe-network-acls --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 --output json",
                "explanation": "NACLs are stateless. Inbound must allow port 22, and outbound must allow ephemeral ports 1024-65535.",
                "what_to_look_for": "Deny rule numbered lower than Allow rule."
            }
        ],
        "verification": "Execute `ssh -v -i key.pem ec2-user@<public-ip>` and confirm the TCP handshake succeeds (OpenSSH banner exchange starts).",
        "prevention": [
            "Use AWS Systems Manager (SSM) Session Manager for shell access without exposing port 22 to the public internet.",
            "Use EC2 Instance Connect with specific IP prefixes or client VPN."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html",
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-002",
        "title": "SSH Returns Permission Denied (publickey)",
        "category": "ec2",
        "difficulty": "beginner",
        "severity": "high",
        "symptom": "SSH connection reaches the EC2 instance but fails authentication with: 'ec2-user@203.0.113.10: Permission denied (publickey,gssapi-keyex,gssapi-with-mic)'.",
        "initial_observations": [
            "TCP connection succeeds immediately (no timeout).",
            "SSH debug output shows client offering private key, but server rejects it."
        ],
        "environment": "EC2 Linux instance running Ubuntu or Amazon Linux.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["ssh", "permissions", "keys", "ec2"],
        "possible_causes": [
            {
                "cause": "Wrong default AMI username used (e.g. using ec2-user on Ubuntu or ubuntu on Amazon Linux)",
                "likelihood": "common",
                "evidence_needed": "AMI platform check vs SSH connection username.",
                "remediation": "Connect with the standard username for the AMI: ec2-user for AL2/AL2023, ubuntu for Ubuntu, admin for Debian, centos for CentOS."
            },
            {
                "cause": "Local private key file permissions too open on client machine",
                "likelihood": "common",
                "evidence_needed": "Client SSH warning: 'UNPROTECTED PRIVATE KEY FILE! Permissions 0644 are too open'.",
                "remediation": "Restrict private key permissions: chmod 400 key.pem (Linux/macOS) or icacls reset/grant on Windows."
            },
            {
                "cause": "Wrong private key used (does not match public key in ~/.ssh/authorized_keys)",
                "likelihood": "occasional",
                "evidence_needed": "Fingerprint mismatch between local private key and KeyName assigned in EC2 launch config.",
                "remediation": "Specify the matching private key corresponding to the KeyPairName displayed in EC2 console."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Run SSH in Verbose Mode (-v)",
                "command": "ssh -v -i mykey.pem ec2-user@203.0.113.10",
                "explanation": "Inspect the authentication handshake and identify which identity files are offered.",
                "what_to_look_for": "Check 'Authentications that can continue' and reason for key rejection."
            },
            {
                "order": 2,
                "title": "Verify Instance AMI Platform and Assigned Key Pair Name",
                "command": "aws ec2 describe-instances --instance-ids i-0123456789abcdef0 --query 'Reservations[*].Instances[*].[ImageId,KeyName]' --output table",
                "explanation": "Confirm the official AMI OS type to deduce default username, and verify the KeyName.",
                "what_to_look_for": "Check KeyName matches the private key file you are using."
            },
            {
                "order": 3,
                "title": "Check Local Private Key File Permissions",
                "command": "ls -l mykey.pem",
                "explanation": "OpenSSH clients refuse keys with permissions wider than 0400 or 0600.",
                "what_to_look_for": "Ensure file is readable only by the owner."
            }
        ],
        "verification": "Execute `ssh -i mykey.pem <correct-user>@<public-ip>` and confirm interactive shell prompt opens.",
        "prevention": [
            "Adopt AWS Systems Manager Session Manager to eliminate reliance on SSH key pair files.",
            "Enforce standardized AMI naming and key management via AWS Secrets Manager."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html"
        ]
    },
    {
        "id": "CFA-003",
        "title": "EC2 Instance Fails Status Check (1/2 or 0/2)",
        "category": "ec2",
        "difficulty": "intermediate",
        "severity": "critical",
        "symptom": "AWS Management Console shows 'Status check failed' (1/2 or 0/2 checks passed) for an active EC2 instance.",
        "initial_observations": [
            "System status check failed OR instance status check failed.",
            "Instance may be unreachable via SSH and application traffic."
        ],
        "environment": "EC2 instance running in AWS with attached EBS root volume.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["ec2", "status-check", "hardware", "kernel", "ebs"],
        "possible_causes": [
            {
                "cause": "System Status Check failure (underlying AWS physical hardware/host problem)",
                "likelihood": "occasional",
                "evidence_needed": "SystemStatus.Status == 'impaired' in describe-instance-status.",
                "remediation": "Stop and then Start the EC2 instance (forces migration to a new healthy underlying physical host)."
            },
            {
                "cause": "Instance Status Check failure (guest OS kernel panic, corrupt filesystem, /etc/fstab error)",
                "likelihood": "common",
                "evidence_needed": "InstanceStatus.Status == 'impaired'; console system log shows kernel panic or mount error.",
                "remediation": "Retrieve EC2 system log. If fstab/kernel corrupt, detach root volume, attach to rescue instance, fix fstab/grub, reattach."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Query Specific Status Check State",
                "command": "aws ec2 describe-instance-status --instance-ids i-0123456789abcdef0",
                "explanation": "Distinguish between SystemStatus (AWS hardware) and InstanceStatus (guest OS).",
                "what_to_look_for": "Look at SystemStatus.Status and InstanceStatus.Status fields."
            },
            {
                "order": 2,
                "title": "Retrieve EC2 Console Output (System Log)",
                "command": "aws ec2 get-console-output --instance-id i-0123456789abcdef0 --output text",
                "explanation": "Inspect boot log for kernel panics, OOM conditions, or bad /etc/fstab entries.",
                "what_to_look_for": "Look for 'Emergency mode', 'fsck failed', or 'Kernel panic'."
            }
        ],
        "verification": "After remediation, monitor `aws ec2 describe-instance-status` until both checks return 'passed'.",
        "prevention": [
            "Configure CloudWatch alarm with EC2 auto-recovery action for System Status check failures.",
            "Use 'nofail' mount options in /etc/fstab for non-root volumes."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-system-instance-status-check.html"
        ]
    },
    {
        "id": "CFA-004",
        "title": "EC2 Running but Application Unreachable",
        "category": "ec2",
        "difficulty": "beginner",
        "severity": "high",
        "symptom": "EC2 instance status is 2/2 passed, SSH works, but HTTP/HTTPS web requests fail or connection is refused.",
        "initial_observations": [
            "Instance responds to ping and SSH.",
            "curl http://<ip> returns 'Connection refused' or hangs."
        ],
        "environment": "EC2 running Nginx/Node.js web application.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["ec2", "application", "ports", "systemd"],
        "possible_causes": [
            {
                "cause": "Application process or web server stopped or crashed",
                "likelihood": "common",
                "evidence_needed": "systemctl status shows inactive or failed.",
                "remediation": "Restart service using `sudo systemctl start nginx` and inspect error logs."
            },
            {
                "cause": "Process listening only on localhost (127.0.0.1) instead of 0.0.0.0",
                "likelihood": "common",
                "evidence_needed": "ss -tlnp shows 127.0.0.1:8080 rather than 0.0.0.0:8080.",
                "remediation": "Update application host binding configuration from 'localhost' / '127.0.0.1' to '0.0.0.0'."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Test Local Loopback Connectivity Inside Instance",
                "command": "curl -I http://127.0.0.1:80",
                "explanation": "Verify if the web server responds to local requests inside the instance.",
                "what_to_look_for": "HTTP 200/301 response vs 'Failed to connect'."
            },
            {
                "order": 2,
                "title": "Inspect Listening TCP Sockets and Bound Interfaces",
                "command": "sudo ss -tlnp",
                "explanation": "Determine which processes are listening on which ports and IP addresses.",
                "what_to_look_for": "Look for 0.0.0.0:80 or :::80 in the Local Address column."
            }
        ],
        "verification": "curl -I http://<public-ip>:80 returns valid HTTP response.",
        "prevention": [
            "Enable systemd service auto-restart with `Restart=always`.",
            "Configure process monitoring with Monit or CloudWatch agent."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-005",
        "title": "EC2 Outbound Internet Access Fails",
        "category": "ec2",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "Instance cannot run `yum update` or reach external APIs (curl https://aws.amazon.com hangs).",
        "initial_observations": [
            "Inbound SSH works, but outbound HTTP/HTTPS times out.",
            "DNS queries may fail or hang."
        ],
        "environment": "EC2 in VPC subnet.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["ec2", "networking", "egress", "security-groups"],
        "possible_causes": [
            {
                "cause": "Security Group outbound rules deleted or restricted",
                "likelihood": "common",
                "evidence_needed": "describe-security-groups showing no egress rule for 0.0.0.0/0.",
                "remediation": "Add egress rule allowing all traffic (or TCP 80/443) to 0.0.0.0/0."
            },
            {
                "cause": "Subnet route table has no route to IGW or NAT Gateway",
                "likelihood": "common",
                "evidence_needed": "Route table missing 0.0.0.0/0 destination.",
                "remediation": "Add 0.0.0.0/0 route to Internet Gateway (if public) or NAT Gateway (if private)."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect Security Group Egress Rules",
                "command": "aws ec2 describe-security-groups --group-ids sg-xxxx --query 'SecurityGroups[*].IpPermissionsEgress'",
                "explanation": "Verify outbound rules allow egress.",
                "what_to_look_for": "Look for 0.0.0.0/0 allow rule."
            },
            {
                "order": 2,
                "title": "Check Subnet Route Table",
                "command": "aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=subnet-xxxx",
                "explanation": "Check for default gateway route.",
                "what_to_look_for": "Default route pointing to igw or nat."
            }
        ],
        "verification": "Run `curl -I https://aws.amazon.com` inside instance and verify 200/301 status.",
        "prevention": [
            "Do not remove default allow-all egress rule from Security Groups unless egress proxy is deployed."
        ],
        "references": [
            "https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html"
        ]
    },
    {
        "id": "CFA-006",
        "title": "EC2 Instance Unable to Access S3",
        "category": "iam-s3",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "Application or CLI running on EC2 returns 'Unable to locate credentials' or 'AccessDenied' when running `aws s3 ls s3://my-bucket`.",
        "initial_observations": [
            "Instance is running.",
            "Command fails when accessing AWS APIs from within the instance."
        ],
        "environment": "EC2 instance with or without an attached IAM Instance Profile.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["ec2", "iam", "s3", "instance-profile", "imds"],
        "possible_causes": [
            {
                "cause": "No IAM Instance Profile attached to the EC2 instance",
                "likelihood": "common",
                "evidence_needed": "describe-instances shows IamInstanceProfile is null.",
                "remediation": "Attach an IAM role to the instance using `aws ec2 associate-iam-instance-profile`."
            },
            {
                "cause": "Attached IAM role lacks s3:GetObject or s3:ListBucket permissions",
                "likelihood": "common",
                "evidence_needed": "IAM role policy does not grant necessary action on target bucket ARN.",
                "remediation": "Update role policy to include required s3 actions on `arn:aws:s3:::my-bucket` and `arn:aws:s3:::my-bucket/*`."
            },
            {
                "cause": "IMDSv2 hop limit prevents container/SDK token retrieval",
                "likelihood": "occasional",
                "evidence_needed": "Instance metadata options show HttpPutResponseHopLimit=1 with containerized app.",
                "remediation": "Increase HttpPutResponseHopLimit to 2 using `aws ec2 modify-instance-metadata-options`."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Attached IAM Instance Profile on EC2 Instance",
                "command": "aws ec2 describe-instances --instance-ids i-0123456789abcdef0 --query 'Reservations[*].Instances[*].IamInstanceProfile'",
                "explanation": "Verify an instance profile is associated with the instance.",
                "what_to_look_for": "Arn and Id of attached instance profile."
            },
            {
                "order": 2,
                "title": "Query IMDS Credentials Endpoint From Inside Instance",
                "command": "curl -H 'X-aws-ec2-metadata-token: ...' http://169.254.169.254/latest/meta-data/iam/security-credentials/",
                "explanation": "Verify instance metadata service is vending credentials.",
                "what_to_look_for": "Role name returned by metadata service."
            },
            {
                "order": 3,
                "title": "Verify Caller Identity and Active IAM Policy",
                "command": "aws sts get-caller-identity",
                "explanation": "Confirm which role credentials the AWS CLI is currently using.",
                "what_to_look_for": "Assumed-role ARN matching expected role name."
            }
        ],
        "verification": "Run `aws s3 ls s3://my-bucket` from instance and verify bucket contents list successfully.",
        "prevention": [
            "Use IAM roles exclusively for EC2 workloads; never store static IAM access keys on instances.",
            "Apply least-privilege IAM policies scoped to specific bucket ARNs."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html",
            "https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html"
        ]
    },
    {
        "id": "CFA-007",
        "title": "Website Returns HTTP 403 Forbidden or 404 Not Found",
        "category": "application",
        "difficulty": "beginner",
        "severity": "medium",
        "symptom": "End users accessing a web application receive HTTP 403 Forbidden or HTTP 404 Not Found response.",
        "initial_observations": [
            "Web server is running and responding.",
            "Specific routes or static assets fail."
        ],
        "environment": "EC2 running Nginx or Apache HTTP Server.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["http", "nginx", "apache", "permissions", "filesystem"],
        "possible_causes": [
            {
                "cause": "Web server worker user lacks read/execute permissions on document root files",
                "likelihood": "common",
                "evidence_needed": "Nginx error.log: 'directory index of /var/www/html is forbidden' or '13: Permission denied'.",
                "remediation": "Fix ownership and permissions: `chown -R nginx:nginx /var/www/html` and `chmod -R 755 /var/www/html`."
            },
            {
                "cause": "Missing index file (index.html or index.php) with directory autoindex disabled",
                "likelihood": "common",
                "evidence_needed": "Directory exists but contains no recognized index file.",
                "remediation": "Create required index.html or configure directory listing if intentional."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Web Server Error Log",
                "command": "sudo tail -n 25 /var/log/nginx/error.log",
                "explanation": "Web server logs state exact reason for 403 or 404.",
                "what_to_look_for": "Look for 'Permission denied' or 'No such file or directory'."
            },
            {
                "order": 2,
                "title": "Verify File Permissions on Document Root",
                "command": "ls -ld /var/www /var/www/html && ls -la /var/www/html",
                "explanation": "Verify read and execute bits on path leading to content.",
                "what_to_look_for": "Owner matching web server user and +r +x permissions."
            }
        ],
        "verification": "curl -I http://localhost returns HTTP 200 OK.",
        "prevention": [
            "Include correct file permission enforcement in CI/CD deployment scripts."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/hosting-websites.html"
        ]
    },
    {
        "id": "CFA-008",
        "title": "Website Returns HTTP 502 Bad Gateway",
        "category": "application",
        "difficulty": "intermediate",
        "severity": "critical",
        "symptom": "Browser displays '502 Bad Gateway' when accessing application via reverse proxy or ALB.",
        "initial_observations": [
            "Proxy server (Nginx or ALB) is reachable.",
            "Backend upstream application service fails to return a valid HTTP response."
        ],
        "environment": "Nginx reverse proxy pointing to upstream Gunicorn/Node.js app.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["http-502", "nginx", "proxy", "alb", "gunicorn"],
        "possible_causes": [
            {
                "cause": "Upstream application process (Node, Gunicorn, PHP-FPM) crashed or not running",
                "likelihood": "common",
                "evidence_needed": "Nginx error log: 'connect() failed (111: Connection refused) while connecting to upstream'.",
                "remediation": "Start or restart backend process with systemctl and inspect application crash trace."
            },
            {
                "cause": "Upstream listening on wrong port or Unix domain socket permission issue",
                "likelihood": "common",
                "evidence_needed": "Socket file missing or owned by wrong user.",
                "remediation": "Ensure backend listens on configured port/socket and socket file permissions allow proxy user access."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Reverse Proxy Error Log",
                "command": "sudo tail -n 30 /var/log/nginx/error.log",
                "explanation": "Identifies whether upstream refused connection, timed out, or sent empty response.",
                "what_to_look_for": "Connection refused or no live upstreams while connecting to upstream."
            },
            {
                "order": 2,
                "title": "Check Status of Upstream Application Service",
                "command": "sudo systemctl status myapp.service",
                "explanation": "Confirm backend application daemon is active.",
                "what_to_look_for": "Active: active (running) vs failed or dead."
            }
        ],
        "verification": "curl -I http://localhost returns HTTP 200.",
        "prevention": [
            "Configure systemd `Restart=always` with `RestartSec=5`.",
            "Implement robust health checks and monitoring."
        ],
        "references": [
            "https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html"
        ]
    },
    {
        "id": "CFA-009",
        "title": "Website Returns HTTP 504 Gateway Timeout",
        "category": "application",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "Clients experience 60+ second page loading delay followed by '504 Gateway Time-out'.",
        "initial_observations": [
            "Reverse proxy or ALB accepts client connection, but backend fails to respond before timeout."
        ],
        "environment": "Application behind Application Load Balancer or Nginx reverse proxy.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["http-504", "timeout", "alb", "database", "slow-query"],
        "possible_causes": [
            {
                "cause": "Backend application blocked on slow database query or external API call",
                "likelihood": "common",
                "evidence_needed": "DB slow query log or high DB CPU; app threads stuck in I/O wait.",
                "remediation": "Optimize slow SQL queries, add database indexes, or introduce caching layer (Redis)."
            },
            {
                "cause": "Backend thread pool saturation / high CPU starvation",
                "likelihood": "occasional",
                "evidence_needed": "High CPU utilization (>95%) or worker queue overflow.",
                "remediation": "Scale backend instances horizontally or increase worker concurrency."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Backend CPU, Memory, and Thread Saturation",
                "command": "top -b -n 1 | head -n 15",
                "explanation": "Evaluate if instance is CPU or memory saturated.",
                "what_to_look_for": "High load average or CPU steal/wait."
            },
            {
                "order": 2,
                "title": "Inspect Proxy Upstream Response Time Logs",
                "command": "sudo awk '{print $NF}' /var/log/nginx/access.log | tail -20",
                "explanation": "Check upstream response time column.",
                "what_to_look_for": "Upstream response times exceeding proxy timeout."
            }
        ],
        "verification": "curl -w 'Total Time: %{time_total}s\\n' -o /dev/null -s http://localhost returns < 1.0s.",
        "prevention": [
            "Implement request timeouts at application layer lower than proxy idle timeout.",
            "Add circuit breakers for external downstream calls."
        ],
        "references": [
            "https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html"
        ]
    },
    {
        "id": "CFA-010",
        "title": "Linux Root Filesystem 100% Full",
        "category": "linux",
        "difficulty": "beginner",
        "severity": "critical",
        "symptom": "Applications crash, services fail to write logs, and shell warns: 'No space left on device'.",
        "initial_observations": [
            "df -h shows / mounted on /dev/xvda1 is at 100% capacity (0 bytes available).",
            "Command line tab completion and temporary files fail."
        ],
        "environment": "Amazon Linux 2 / Ubuntu EC2 instance.",
        "has_runbook": True,
        "has_demo": True,
        "tags": ["linux", "disk", "storage", "df", "du", "logrotate"],
        "possible_causes": [
            {
                "cause": "Unrotated or runaway log files in /var/log",
                "likelihood": "common",
                "evidence_needed": "du -sh /var/log/* reveals single log file tens of gigabytes in size.",
                "remediation": "Truncate runaway log file (`> /var/log/app.log`) and configure proper logrotate policy."
            },
            {
                "cause": "Deleted large files still held open by a running process",
                "likelihood": "occasional",
                "evidence_needed": "lsof +L1 shows unlinked files holding open file descriptors with non-zero size.",
                "remediation": "Restart the process holding the file descriptor open or truncate via `/proc/$PID/fd/$FD`."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Disk Capacity by Mount Point",
                "command": "df -h",
                "explanation": "Identify exactly which filesystem mount is exhausted.",
                "what_to_look_for": "Mount point showing 100% Use% and 0 Available."
            },
            {
                "order": 2,
                "title": "Identify Top Storage-Consuming Directories",
                "command": "sudo du -h --max-depth=1 / 2>/dev/null | sort -hr | head -n 10",
                "explanation": "Recursively isolate which top-level directory contains the excess data.",
                "what_to_look_for": "Directory consuming disproportionate volume of disk space."
            },
            {
                "order": 3,
                "title": "Detect Deleted Files Held Open by Processes",
                "command": "sudo lsof / | grep -i deleted",
                "explanation": "When rm is run on an open file, space is not released until process closes the file handle.",
                "what_to_look_for": "Process name and large size associated with (deleted) file."
            }
        ],
        "verification": "Execute `df -h /` and verify Use% is below 80%.",
        "prevention": [
            "Configure logrotate with size caps and compression.",
            "Set up CloudWatch disk metric alarms using CloudWatch agent."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-011",
        "title": "Linux Inode Exhaustion (0 Inodes Available)",
        "category": "linux",
        "difficulty": "intermediate",
        "severity": "critical",
        "symptom": "Application encounters 'No space left on device', but `df -h` shows gigabytes of free disk capacity.",
        "initial_observations": [
            "df -h reports 40% disk space free.",
            "touch /tmp/testfile fails with 'No space left on device'."
        ],
        "environment": "Linux server hosting web service with extensive temporary or session files.",
        "has_runbook": True,
        "has_demo": True,
        "tags": ["linux", "inodes", "storage", "filesystem", "find"],
        "possible_causes": [
            {
                "cause": "Millions of tiny session or temporary files accumulated in /tmp, /var/spool, or /var/lib/php/sessions",
                "likelihood": "common",
                "evidence_needed": "df -i shows IUse% at 100%; directory contains hundreds of thousands of entries.",
                "remediation": "Clean accumulated orphan session files using find with -delete, and configure cron cleanup job."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Inode Consumption Across Filesystems",
                "command": "df -i",
                "explanation": "Measure inode usage percentage (IUse%) rather than block capacity.",
                "what_to_look_for": "Filesystem showing 100% IUse% and 0 IFree."
            },
            {
                "order": 2,
                "title": "Locate Directories with the Highest File Counts",
                "command": "sudo find / -xdev -printf '%h\\n' | sort | uniq -c | sort -k1 -n | tail -15",
                "explanation": "Count file entries per directory across the filesystem.",
                "what_to_look_for": "Directories containing hundreds of thousands of files."
            }
        ],
        "verification": "Run `df -i /` and confirm IFree > 0 and IUse% < 80%.",
        "prevention": [
            "Set up automated tmpfiles.d or cron cleanup policies for session caches.",
            "Monitor inode usage alongside disk block usage in CloudWatch."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-012",
        "title": "High CPU or Memory Usage / OOM-Killer Triggered",
        "category": "linux",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "Instance is sluggish, SSH sessions lag, and backend process dies unexpectedly with exit code 137.",
        "initial_observations": [
            "High load average.",
            "dmesg shows 'Out of memory: Kill process'."
        ],
        "environment": "EC2 t3.small or t3.medium instance running memory-intensive workloads.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["linux", "memory", "oom", "cpu", "dmesg", "top"],
        "possible_causes": [
            {
                "cause": "Memory leak in application process causing OS Out-Of-Memory (OOM) killer invocation",
                "likelihood": "common",
                "evidence_needed": "dmesg logs showing 'kernel: Out of memory: Kill process <PID> (<name>) score <score>'.",
                "remediation": "Restart service, analyze heap dumps, configure swap file as buffer, and scale instance RAM size."
            },
            {
                "cause": "Runaway worker process consuming 100% CPU",
                "likelihood": "common",
                "evidence_needed": "top shows process at 99.9% %CPU continuously.",
                "remediation": "Identify thread deadlock or infinite loop; restart worker and patch bug."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Real-Time Memory and Process Consumption",
                "command": "free -h && ps aux --sort=-%mem | head -n 10",
                "explanation": "Inspect total, used, and available RAM and top memory consuming processes.",
                "what_to_look_for": "Available memory near 0, process consuming majority of memory."
            },
            {
                "order": 2,
                "title": "Check Kernel Ring Buffer for OOM Killer Events",
                "command": "sudo dmesg -T | grep -iE 'oom|out of memory|killed process' | tail -15",
                "explanation": "Look for explicit Linux kernel OOM killer actions and process termination records.",
                "what_to_look_for": "Timestamped 'Killed process' lines."
            }
        ],
        "verification": "free -h shows healthy available memory and application is running without OOM kills.",
        "prevention": [
            "Enable swap space on EBS volume for burst absorption.",
            "Configure memory limits via systemd cgroups (MemoryMax=...)."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-013",
        "title": "systemd Service Fails to Start (CrashLoop)",
        "category": "linux",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "`systemctl start myapp` fails with 'Job for myapp.service failed because the control process exited with error code'.",
        "initial_observations": [
            "Service status shows Active: failed (Result: exit-code).",
            "Main PID exited with error code (status=1/FAILURE or status=127)."
        ],
        "environment": "Systemd managed Linux host.",
        "has_runbook": True,
        "has_demo": True,
        "tags": ["linux", "systemd", "journalctl", "services"],
        "possible_causes": [
            {
                "cause": "Address already in use (another process already listening on the configured port)",
                "likelihood": "common",
                "evidence_needed": "journalctl shows 'bind: Address already in use' or 'EADDRINUSE'.",
                "remediation": "Identify conflicting process using `ss -tlnp` and stop it or adjust configuration port."
            },
            {
                "cause": "Missing executable or wrong path specified in ExecStart directive (exit status 127)",
                "likelihood": "common",
                "evidence_needed": "journalctl shows 'Failed at step EXEC spawning ...: No such file or directory'.",
                "remediation": "Update ExecStart path in unit file to the absolute path of the verified binary, run daemon-reload."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect Service Status and Exit Reason",
                "command": "systemctl status myapp.service -l --no-pager",
                "explanation": "Check unit state, PID, exit code, and recent log snippets.",
                "what_to_look_for": "Status code and error line."
            },
            {
                "order": 2,
                "title": "Review Full Unit Journal Logs",
                "command": "sudo journalctl -u myapp.service -b -e --no-pager -n 50",
                "explanation": "View stdout/stderr emitted by the service process before death.",
                "what_to_look_for": "Stack traces, missing config files, or port binding errors."
            }
        ],
        "verification": "systemctl is-active myapp.service returns 'active'.",
        "prevention": [
            "Validate configuration files before restarting systemd services.",
            "Use `systemctl daemon-reload` whenever unit files are edited."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-014",
        "title": "Linux File Permission Denied and POSIX ACL Mask Issue",
        "category": "linux",
        "difficulty": "intermediate",
        "severity": "medium",
        "symptom": "User or service receives 'Permission denied' trying to read or execute a file despite group membership.",
        "initial_observations": [
            "ls -la displays permissions ending in '+' symbol.",
            "Standard chmod does not grant expected access."
        ],
        "environment": "Linux server using POSIX Access Control Lists (ACLs).",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["linux", "permissions", "acls", "getfacl", "setfacl"],
        "possible_causes": [
            {
                "cause": "POSIX ACL mask restricts effective permissions or parent directory lacks execute (x) traversal bit",
                "likelihood": "common",
                "evidence_needed": "getfacl shows `mask::r--` or parent directory is `drw-r--r--`.",
                "remediation": "Fix parent directory traversal bit (`chmod +x parent_dir`) and adjust ACL mask (`setfacl -m m::rwx file`)."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect File and Parent Directory POSIX ACLs",
                "command": "getfacl /path/to/target_file",
                "explanation": "Retrieve extended ACL permissions and effective mask.",
                "what_to_look_for": "Look for #effective: annotations and mask line."
            },
            {
                "order": 2,
                "title": "Check Parent Directory Traversal (Execute) Permission",
                "command": "namei -l /path/to/target_file",
                "explanation": "Step through every directory in the path to verify traversal permissions.",
                "what_to_look_for": "Any parent directory missing execute (x) bit for the executing user."
            }
        ],
        "verification": "Execute `sudo -u <target-user> cat /path/to/target_file` successfully.",
        "prevention": [
            "Standardize file ownership and use POSIX groups rather than ad-hoc user ACLs where possible."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-015",
        "title": "Process Cannot Bind to Port (EADDRINUSE)",
        "category": "linux",
        "difficulty": "beginner",
        "severity": "medium",
        "symptom": "Starting application fails with error: 'bind: Address already in use' or port collision.",
        "initial_observations": [
            "Previous instance of daemon was killed or crashed.",
            "Port 80, 443, or 8080 cannot be bound."
        ],
        "environment": "Linux server.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["linux", "networking", "ports", "ss", "lsof"],
        "possible_causes": [
            {
                "cause": "Orphaned or zombie daemon process still holding the listening socket",
                "likelihood": "common",
                "evidence_needed": "ss -tlnp shows existing PID bound to target port.",
                "remediation": "Terminate rogue process via `kill -15 <PID>` (or `kill -9 <PID>` if unresponsive)."
            },
            {
                "cause": "Socket currently lingering in TIME_WAIT state",
                "likelihood": "occasional",
                "evidence_needed": "ss -tan shows socket state TIME_WAIT.",
                "remediation": "Enable SO_REUSEADDR in application server configuration."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Identify Process Holding the Port",
                "command": "sudo ss -tlnp 'sport = :8080'",
                "explanation": "List PID and program name currently bound to the port.",
                "what_to_look_for": "users:((\"node\",pid=1234,fd=19))."
            }
        ],
        "verification": "Application starts and successfully opens listening socket.",
        "prevention": [
            "Configure graceful process shutdown and SO_REUSEADDR socket option."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-016",
        "title": "EBS Volume Expanded but Linux Filesystem Not Resized",
        "category": "linux",
        "difficulty": "intermediate",
        "severity": "medium",
        "symptom": "AWS console shows EBS volume size increased from 20GB to 50GB, but `df -h` still displays 20GB available.",
        "initial_observations": [
            "lsblk shows disk is 50G, but partition or filesystem is 20G.",
            "df -h reflects the old size."
        ],
        "environment": "EC2 instance with modified EBS volume (ext4 or xfs).",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["ebs", "storage", "filesystem", "growpart", "resize2fs", "xfs_growfs"],
        "possible_causes": [
            {
                "cause": "Partition and filesystem have not been grown to fill the new block device boundary",
                "likelihood": "common",
                "evidence_needed": "lsblk shows xvda is 50G but xvda1 is 20G.",
                "remediation": "Run `sudo growpart /dev/xvda 1` to expand partition, followed by `sudo resize2fs /dev/xvda1` (ext4) or `sudo xfs_growfs -d /` (XFS)."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Compare Block Devices vs Filesystems",
                "command": "lsblk && df -hT",
                "explanation": "Inspect hardware block size vs partition table vs mounted filesystem.",
                "what_to_look_for": "Discrepancy between root disk size and partition size."
            }
        ],
        "verification": "df -h / shows updated 50GB size.",
        "prevention": [
            "Include filesystem resize commands in provisioning automation after EBS volume modification."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/recognize-expanded-volume-linux.html"
        ]
    },
    {
        "id": "CFA-017",
        "title": "Application Load Balancer Reports Unhealthy Targets",
        "category": "networking",
        "difficulty": "intermediate",
        "severity": "critical",
        "symptom": "ALB target group shows all registered targets with Status: 'Unhealthy' and reason 'Target.Timeout' or 'Target.ResponseCodeMismatch'.",
        "initial_observations": [
            "ALB returns HTTP 502 or 503 to web clients.",
            "Targets are in running state in EC2 console."
        ],
        "environment": "AWS ALB routing to EC2 target group.",
        "has_runbook": True,
        "has_demo": True,
        "tags": ["alb", "target-group", "health-check", "networking", "security-groups"],
        "possible_causes": [
            {
                "cause": "Target Security Group blocks traffic coming from the ALB Security Group",
                "likelihood": "common",
                "evidence_needed": "Health check reason is Target.Timeout; EC2 SG has no inbound rule for ALB SG.",
                "remediation": "Add an inbound rule to target SG permitting traffic on target port with source set to ALB Security Group ID."
            },
            {
                "cause": "Health check path returns HTTP status outside the configured matcher (e.g. 404 or 301 vs expected 200)",
                "likelihood": "common",
                "evidence_needed": "Health check reason is Target.ResponseCodeMismatch [status: 404].",
                "remediation": "Update Target Group health check path to a valid endpoint or update application routing."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Query Target Health and Specific Reason Codes",
                "command": "aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:... --output table",
                "explanation": "Retrieve specific health check failure reason for each target.",
                "what_to_look_for": "TargetHealth.Reason (e.g. Target.Timeout, Target.ResponseCodeMismatch)."
            },
            {
                "order": 2,
                "title": "Test Health Check Endpoint Directly from Within VPC",
                "command": "curl -Iv http://<target-private-ip>:<health-port>/<health-path>",
                "explanation": "Observe the exact HTTP response code and headers returned by the target.",
                "what_to_look_for": "HTTP response code vs Target Group matcher setting."
            }
        ],
        "verification": "Target health transitions to 'healthy' in `describe-target-health`.",
        "prevention": [
            "Dedicate a lightweight `/healthz` endpoint returning HTTP 200 that does not require database access or authentication.",
            "Use Security Group reference rules instead of static CIDR ranges."
        ],
        "references": [
            "https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html"
        ]
    },
    {
        "id": "CFA-018",
        "title": "Private Subnet Instance Cannot Access Internet via NAT Gateway",
        "category": "networking",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "EC2 instance in a private subnet cannot connect to external internet endpoints (yum, external APIs).",
        "initial_observations": [
            "Instance has private IP only.",
            "Traffic destined for 0.0.0.0/0 is dropped."
        ],
        "environment": "AWS VPC with public subnet, private subnet, and NAT Gateway.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["vpc", "nat-gateway", "networking", "routing", "private-subnet"],
        "possible_causes": [
            {
                "cause": "NAT Gateway was mistakenly placed in the private subnet instead of the public subnet",
                "likelihood": "common",
                "evidence_needed": "NAT Gateway subnet lacks route to Internet Gateway.",
                "remediation": "Deploy NAT Gateway in a public subnet that has an explicit route to an Internet Gateway."
            },
            {
                "cause": "Private subnet route table missing default route to the NAT Gateway (0.0.0.0/0 -> nat-xxx)",
                "likelihood": "common",
                "evidence_needed": "Private route table only contains local VPC CIDR route.",
                "remediation": "Add route 0.0.0.0/0 with target set to the NAT Gateway ID."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect Route Table Associated with Private Subnet",
                "command": "aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=subnet-private --query 'RouteTables[*].Routes'",
                "explanation": "Confirm private subnet routes 0.0.0.0/0 to nat-xxxxxxxx.",
                "what_to_look_for": "Destination 0.0.0.0/0 with NatGatewayId."
            },
            {
                "order": 2,
                "title": "Verify NAT Gateway Placement Subnet and Public Route",
                "command": "aws ec2 describe-nat-gateways --nat-gateway-ids nat-xxxx",
                "explanation": "Check which subnet hosts the NAT Gateway and verify that subnet's route table.",
                "what_to_look_for": "NAT Gateway's subnet must have an igw-xxxx default route."
            }
        ],
        "verification": "From private instance: `curl -I https://checkip.amazonaws.com` returns successfully.",
        "prevention": [
            "Use VPC Reachability Analyzer to validate end-to-end paths before going to production."
        ],
        "references": [
            "https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-troubleshooting.html"
        ]
    },
    {
        "id": "CFA-019",
        "title": "VPC DNS Resolution Failure",
        "category": "networking",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "Instances in VPC cannot resolve public domain names or private Route 53 zones; `nslookup` times out.",
        "initial_observations": [
            "Ping to public IP (8.8.8.8) succeeds, but domain lookups fail.",
            "AmazonProvidedDNS fails to respond."
        ],
        "environment": "Custom VPC in AWS.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["vpc", "dns", "route53", "networking", "dhcp"],
        "possible_causes": [
            {
                "cause": "VPC attribute `enableDnsSupport` is set to false",
                "likelihood": "common",
                "evidence_needed": "describe-vpc-attribute returns EnableDnsSupport.Value: false.",
                "remediation": "Enable DNS support: `aws ec2 modify-vpc-attribute --vpc-id vpc-xxx --enable-dns-support '{\"Value\": true}'`."
            },
            {
                "cause": "Custom DHCP option set points to unreachable external DNS servers",
                "likelihood": "occasional",
                "evidence_needed": "cat /etc/resolv.conf points to non-Amazon IP that drops traffic.",
                "remediation": "Update DHCP option set to use AmazonProvidedDNS or valid corporate forwarder."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check VPC DNS Attributes",
                "command": "aws ec2 describe-vpc-attribute --vpc-id vpc-xxxx --attribute enableDnsSupport && aws ec2 describe-vpc-attribute --vpc-id vpc-xxxx --attribute enableDnsHostnames",
                "explanation": "Verify both DNS support and DNS hostnames are enabled on the VPC.",
                "what_to_look_for": "Value: false on enableDnsSupport."
            },
            {
                "order": 2,
                "title": "Check Guest OS /etc/resolv.conf Configuration",
                "command": "cat /etc/resolv.conf",
                "explanation": "Confirm nameserver points to the AmazonProvidedDNS (VPC base + 2 or 169.254.169.253).",
                "what_to_look_for": "nameserver entry matching VPC CIDR base + 2."
            }
        ],
        "verification": "Run `dig amazon.com` and confirm NOERROR status with valid Answer section.",
        "prevention": [
            "Ensure IaC templates (Terraform/CloudFormation) explicitly set `enable_dns_support = true`."
        ],
        "references": [
            "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns.html"
        ]
    },
    {
        "id": "CFA-020",
        "title": "S3 AccessDenied 403 / Bucket Policy Explicit Deny",
        "category": "iam-s3",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "IAM principal receives 'An error occurred (AccessDenied) when calling the GetObject operation' accessing S3 bucket.",
        "initial_observations": [
            "Principal has AdministratorAccess IAM policy attached.",
            "Request is still denied by Amazon S3."
        ],
        "environment": "Amazon S3 bucket with Bucket Policy.",
        "has_runbook": True,
        "has_demo": True,
        "tags": ["s3", "iam", "bucket-policy", "access-denied", "explicit-deny"],
        "possible_causes": [
            {
                "cause": "Explicit Deny statement in the S3 Bucket Policy overrides IAM Allow",
                "likelihood": "common",
                "evidence_needed": "Bucket policy contains Statement with Effect: Deny matching principal or missing Condition exception.",
                "remediation": "Audit bucket policy conditions (e.g. aws:PrincipalArn, aws:sourceVpce, aws:SecureTransport) and update."
            },
            {
                "cause": "S3 Block Public Access enabled at account or bucket level blocking access",
                "likelihood": "common",
                "evidence_needed": "GetPublicAccessBlock returns BlockPublicPolicy: true.",
                "remediation": "Review and configure Block Public Access settings if public/cross-account access was intended."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Retrieve and Inspect S3 Bucket Policy",
                "command": "aws s3api get-bucket-policy --bucket my-bucket --query Policy --output text | jq .",
                "explanation": "Look for explicit Deny statements that override identity permissions.",
                "what_to_look_for": "Effect: Deny blocks and condition logic."
            },
            {
                "order": 2,
                "title": "Check Bucket and Account Public Access Block",
                "command": "aws s3api get-public-access-block --bucket my-bucket",
                "explanation": "Verify if BlockPublicAccess settings reject the request.",
                "what_to_look_for": "True values on BlockPublicPolicy or RestrictPublicBuckets."
            }
        ],
        "verification": "Run `aws s3 cp s3://my-bucket/test.txt .` and confirm download succeeds.",
        "prevention": [
            "Use IAM Policy Simulator to test policy evaluations before deploying bucket policies.",
            "Always include NotPrincipal or Condition exclusions when using broad Deny statements."
        ],
        "references": [
            "https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html"
        ]
    },
    {
        "id": "CFA-021",
        "title": "AWS CLI Using Wrong Account, Profile, or Region",
        "category": "iam-s3",
        "difficulty": "beginner",
        "severity": "medium",
        "symptom": "AWS CLI commands execute against the wrong AWS account or region, creating resources in unintended locations.",
        "initial_observations": [
            "Command executed without error, but resources do not appear in expected console.",
            "Resource not found errors when querying existing resources."
        ],
        "environment": "Developer or engineer workstation with multiple AWS profiles.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["aws-cli", "credentials", "profiles", "iam", "configuration"],
        "possible_causes": [
            {
                "cause": "Environment variable (AWS_PROFILE or AWS_DEFAULT_REGION) overriding credentials file",
                "likelihood": "common",
                "evidence_needed": "aws configure list shows TYPE: env overriding config file.",
                "remediation": "Clear environment variables (`unset AWS_PROFILE AWS_DEFAULT_REGION`) or set intentionally."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Active Configuration Precedence",
                "command": "aws configure list",
                "explanation": "Display which configuration source is determining profile, region, and credentials.",
                "what_to_look_for": "Look at TYPE column (env, shared-credentials-file, config-file)."
            },
            {
                "order": 2,
                "title": "Verify Authenticated IAM Caller Identity",
                "command": "aws sts get-caller-identity",
                "explanation": "Print Account ID, UserId, and Arn of current credentials.",
                "what_to_look_for": "Account ID matching intended environment."
            }
        ],
        "verification": "aws sts get-caller-identity displays correct 12-digit Account ID.",
        "prevention": [
            "Use prompt tools like `aws-vault` or `starship` to visibly display current AWS profile in shell prompt."
        ],
        "references": [
            "https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html"
        ]
    },
    {
        "id": "CFA-022",
        "title": "S3 KMS-Encrypted Object AccessDenied",
        "category": "iam-s3",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "User has full S3 permissions but receives AccessDenied specifically when downloading encrypted S3 objects.",
        "initial_observations": [
            "s3:ListBucket succeeds.",
            "s3:GetObject fails with AccessDenied on objects encrypted with customer-managed KMS key (SSE-KMS)."
        ],
        "environment": "S3 bucket with SSE-KMS encryption enabled.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["s3", "kms", "encryption", "iam", "key-policy"],
        "possible_causes": [
            {
                "cause": "Caller lacks kms:Decrypt permission on the AWS KMS key used to encrypt the S3 object",
                "likelihood": "common",
                "evidence_needed": "KMS Key Policy does not authorize the caller's IAM principal for kms:Decrypt.",
                "remediation": "Update the KMS Key Policy to allow caller's principal `kms:Decrypt` and `kms:GenerateDataKey`."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Object Encryption Metadata",
                "command": "aws s3api head-object --bucket my-bucket --key file.txt",
                "explanation": "Identify the KMS key ARN (SSEKMSKeyId) used to encrypt the object.",
                "what_to_look_for": "SSEKMSKeyId in output."
            },
            {
                "order": 2,
                "title": "Inspect KMS Key Policy",
                "command": "aws kms get-key-policy --key-id <key-arn> --policy-name default --output text | jq .",
                "explanation": "Check if KMS key policy grants access to caller principal.",
                "what_to_look_for": "Missing principal in KMS policy statement."
            }
        ],
        "verification": "aws s3 cp s3://my-bucket/file.txt . downloads successfully.",
        "prevention": [
            "Include IAM roles in KMS key policy when configuring bucket default encryption with CMKs."
        ],
        "references": [
            "https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html"
        ]
    },
    {
        "id": "CFA-023",
        "title": "CloudWatch Alarm Does Not Trigger Action",
        "category": "monitoring",
        "difficulty": "intermediate",
        "severity": "medium",
        "symptom": "CloudWatch metric breached threshold, but no SNS email was sent and alarm remains in INSUFFICIENT_DATA or OK.",
        "initial_observations": [
            "Expected alert was never received.",
            "Alarm history shows no state transition to ALARM."
        ],
        "environment": "AWS CloudWatch Alarm with SNS topic subscription.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["cloudwatch", "sns", "monitoring", "alarms"],
        "possible_causes": [
            {
                "cause": "Alarm metric dimension mismatch (e.g. alarm configured for different instance ID or dimension)",
                "likelihood": "common",
                "evidence_needed": "Metric dimensions in alarm definition do not match emitted metric dimensions.",
                "remediation": "Update alarm dimensions to match exact metric namespace and dimension key-values."
            },
            {
                "cause": "Actions only trigger on state TRANSITIONS (OK -> ALARM); alarm was already in ALARM",
                "likelihood": "common",
                "evidence_needed": "Alarm history shows no new state transition occurred during breach.",
                "remediation": "Acknowledge that CloudWatch alarms notify only when state changes, not on each evaluation period."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect Alarm Evaluation History",
                "command": "aws cloudwatch describe-alarm-history --alarm-name my-alarm --max-items 10 --output table",
                "explanation": "Review timestamps of every state evaluation and action execution.",
                "what_to_look_for": "HistoryItemType Action or StateUpdate entries."
            }
        ],
        "verification": "Alarm history records successful execution of SNS publish action on state change.",
        "prevention": [
            "Set appropriate 'Treat missing data as' policy (e.g. treat as breaching for availability alarms)."
        ],
        "references": [
            "https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html"
        ]
    },
    {
        "id": "CFA-024",
        "title": "Application Cannot Connect to RDS Database",
        "category": "monitoring",
        "difficulty": "intermediate",
        "severity": "critical",
        "symptom": "Application crashes with 'OperationalError: (2003, \"Can't connect to MySQL server on 'rds-db.xxx.rds.amazonaws.com' (110)\")'.",
        "initial_observations": [
            "RDS instance status is 'Available'.",
            "Connection hangs and eventually times out (code 110)."
        ],
        "environment": "EC2 application instance connecting to AWS RDS MySQL/PostgreSQL in same VPC.",
        "has_runbook": True,
        "has_demo": False,
        "tags": ["rds", "mysql", "database", "security-groups", "vpc"],
        "possible_causes": [
            {
                "cause": "RDS DB Security Group does not allow inbound traffic from EC2 instance Security Group",
                "likelihood": "common",
                "evidence_needed": "RDS security group ingress rules do not contain EC2 SG ID or CIDR on port 3306/5432.",
                "remediation": "Add ingress rule to RDS Security Group allowing port 3306 (or 5432) with source set to EC2 Security Group ID."
            },
            {
                "cause": "RDS placed in different VPC or subnet without routing/peering",
                "likelihood": "occasional",
                "evidence_needed": "EC2 and RDS VPC IDs differ with no VPC peering connection active.",
                "remediation": "Move RDS to same VPC or configure VPC Peering / Transit Gateway."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Test Network Socket Reachability",
                "command": "nc -zv -w 5 rds-endpoint.xxx.rds.amazonaws.com 3306",
                "explanation": "Verify TCP layer connectivity to database port without running database driver.",
                "what_to_look_for": "Connected vs Connection timed out."
            },
            {
                "order": 2,
                "title": "Inspect RDS Security Group Ingress Rules",
                "command": "aws rds describe-db-instances --db-instance-identifier my-db --query 'DBInstances[*].VpcSecurityGroups'",
                "explanation": "Identify attached security groups and inspect their rules.",
                "what_to_look_for": "Check security group ID and inbound rule for app port."
            }
        ],
        "verification": "Run `nc -zv rds-endpoint.xxx.rds.amazonaws.com 3306` and confirm 'open' connection.",
        "prevention": [
            "Reference security groups by ID across application and database tiers rather than hardcoded IP addresses."
        ],
        "references": [
            "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Troubleshooting.html"
        ]
    },
    {
        "id": "CFA-025",
        "title": "Two EC2 Instances in Same VPC Cannot Communicate",
        "category": "networking",
        "difficulty": "beginner",
        "severity": "high",
        "symptom": "Instance A cannot reach Instance B on internal private IP (`ping 10.0.2.15` fails or times out).",
        "initial_observations": [
            "Both instances are in the same VPC but different subnets.",
            "Local OS firewall or Security Group drops traffic."
        ],
        "environment": "AWS VPC with multiple subnets.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["vpc", "networking", "security-groups", "ping", "nacl"],
        "possible_causes": [
            {
                "cause": "Instance B Security Group does not allow traffic from Instance A Security Group",
                "likelihood": "common",
                "evidence_needed": "Security Group B ingress rules do not reference SG A or Subnet A CIDR.",
                "remediation": "Add ingress rule in SG B allowing desired protocol/port from SG A."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Security Group Rules on Both Instances",
                "command": "aws ec2 describe-security-groups --group-ids sg-instA sg-instB",
                "explanation": "Verify ingress on target instance allows source instance.",
                "what_to_look_for": "Missing rule for ICMP or TCP port."
            }
        ],
        "verification": "Ping or curl from Instance A to Instance B succeeds.",
        "prevention": [
            "Use VPC-wide internal security group allowing internal communication where required."
        ],
        "references": [
            "https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html"
        ]
    },
    {
        "id": "CFA-026",
        "title": "Public Subnet Instance Unreachable (Missing Public IP)",
        "category": "networking",
        "difficulty": "beginner",
        "severity": "medium",
        "symptom": "Instance launched in public subnet with IGW route cannot be reached from internet.",
        "initial_observations": [
            "Subnet has IGW route.",
            "Instance has private IP (10.0.1.50) but no Public IPv4 address."
        ],
        "environment": "AWS VPC public subnet.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["vpc", "public-ip", "elastic-ip", "ec2"],
        "possible_causes": [
            {
                "cause": "Auto-assign public IPv4 address was disabled on subnet and instance launch",
                "likelihood": "common",
                "evidence_needed": "describe-instances shows PublicIpAddress is null or missing.",
                "remediation": "Allocate and associate an Elastic IP (EIP) to the instance's network interface."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect Instance Public IP Assignment",
                "command": "aws ec2 describe-instances --instance-ids i-xxxx --query 'Reservations[*].Instances[*].PublicIpAddress'",
                "explanation": "Check if a public IP exists on the primary network interface.",
                "what_to_look_for": "Null or empty result."
            }
        ],
        "verification": "Public IP assigned and reachable via ping or SSH.",
        "prevention": [
            "Enable 'MapPublicIpOnLaunch' attribute on public subnets."
        ],
        "references": [
            "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-ip-addressing.html"
        ]
    },
    {
        "id": "CFA-027",
        "title": "Application Fails After EC2 Instance Reboot",
        "category": "linux",
        "difficulty": "beginner",
        "severity": "high",
        "symptom": "EC2 instance rebooted cleanly, but application is down and website returns connection refused.",
        "initial_observations": [
            "Instance is running.",
            "systemctl is-enabled shows 'disabled' for the service."
        ],
        "environment": "Linux EC2 instance.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["linux", "systemd", "reboot", "automation"],
        "possible_causes": [
            {
                "cause": "Service unit was never enabled for autostart across reboots",
                "likelihood": "common",
                "evidence_needed": "systemctl is-enabled myapp returns 'disabled'.",
                "remediation": "Run `sudo systemctl enable myapp` and `sudo systemctl start myapp`."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check Service Autostart State",
                "command": "systemctl is-enabled myapp.service",
                "explanation": "Check if unit has symlink in multi-user.target.wants.",
                "what_to_look_for": "disabled."
            }
        ],
        "verification": "systemctl is-enabled returns 'enabled'.",
        "prevention": [
            "Always run `systemctl enable --now <service>` during provisioning."
        ],
        "references": [
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-028",
        "title": "HTTPS / TLS Certificate Failure on Custom Domain",
        "category": "application",
        "difficulty": "intermediate",
        "severity": "high",
        "symptom": "Browser displays 'Your connection is not private' (SSL_ERROR_BAD_CERT_DOMAIN or CERT_HAS_EXPIRED).",
        "initial_observations": [
            "HTTP works or redirects to HTTPS.",
            "HTTPS handshake fails with certificate validation error."
        ],
        "environment": "AWS ACM certificate attached to ALB or CloudFront distribution.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["tls", "ssl", "acm", "cloudfront", "certificates"],
        "possible_causes": [
            {
                "cause": "ACM certificate was requested in wrong region (CloudFront requires us-east-1)",
                "likelihood": "common",
                "evidence_needed": "CloudFront distribution cannot attach certificate created in eu-west-1.",
                "remediation": "Request ACM certificate specifically in us-east-1 for CloudFront distributions."
            },
            {
                "cause": "Certificate domain list does not include the accessed subdomain (e.g. www missing)",
                "likelihood": "common",
                "evidence_needed": "openssl s_client shows Subject Alternative Names missing visited domain.",
                "remediation": "Request new certificate with Subject Alternative Names covering both domain.com and *.domain.com."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Inspect Live SSL Certificate Chain",
                "command": "openssl s_client -connect mydomain.com:443 -servername mydomain.com < /dev/null 2>/dev/null | openssl x509 -noout -text",
                "explanation": "Examine validity dates, issuer, and Subject Alternative Names (SAN).",
                "what_to_look_for": "Validity Not After date and X509v3 Subject Alternative Name list."
            }
        ],
        "verification": "curl -Iv https://mydomain.com reports successful TLS handshake and valid certificate.",
        "prevention": [
            "Use AWS ACM managed DNS validation for automatic certificate renewals."
        ],
        "references": [
            "https://docs.aws.amazon.com/acm/latest/userguide/troubleshooting.html"
        ]
    },
    {
        "id": "CFA-029",
        "title": "Route 53 DNS Resolution Returns Stale IP",
        "category": "networking",
        "difficulty": "intermediate",
        "severity": "medium",
        "symptom": "DNS record was updated in Route 53, but clients continue resolving the old IP address.",
        "initial_observations": [
            "Route 53 console shows new IP.",
            "Local `dig` or `nslookup` queries still return old IP."
        ],
        "environment": "AWS Route 53 Hosted Zone.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["route53", "dns", "ttl", "networking"],
        "possible_causes": [
            {
                "cause": "High DNS TTL (Time To Live) causing public resolvers to cache old record",
                "likelihood": "common",
                "evidence_needed": "Querying Route 53 authoritative nameserver returns new IP, but public 8.8.8.8 returns old IP.",
                "remediation": "Wait for TTL expiration or lower TTL to 60 seconds well in advance of planned migrations."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Query Route 53 Authoritative Nameservers Directly",
                "command": "dig @ns-xxxx.awsdns-xx.com mydomain.com A +noall +answer",
                "explanation": "Bypass recursive resolver caching by querying authoritative nameservers directly.",
                "what_to_look_for": "Verify authoritative server immediately returns updated IP."
            }
        ],
        "verification": "dig mydomain.com returns the updated IP address across public resolvers.",
        "prevention": [
            "Lower TTL to 60-300 seconds 24-48 hours prior to DNS migrations."
        ],
        "references": [
            "https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/troubleshooting-new-dns-settings-not-in-effect.html"
        ]
    },
    {
        "id": "CFA-030",
        "title": "CloudWatch Agent Missing Memory and Disk Metrics",
        "category": "monitoring",
        "difficulty": "intermediate",
        "severity": "medium",
        "symptom": "EC2 dashboard shows CPU and network metrics, but memory and disk utilization metrics are missing.",
        "initial_observations": [
            "CloudWatch default metrics exist.",
            "Custom namespace CWAgent has no data points."
        ],
        "environment": "EC2 instance with CloudWatch agent installed.",
        "has_runbook": False,
        "has_demo": False,
        "tags": ["cloudwatch", "cwagent", "metrics", "iam", "monitoring"],
        "possible_causes": [
            {
                "cause": "EC2 instance role lacks CloudWatchAgentServerPolicy IAM permissions",
                "likelihood": "common",
                "evidence_needed": "/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log shows AccessDenied writing metric data.",
                "remediation": "Attach managed policy `CloudWatchAgentServerPolicy` to the instance's IAM role."
            },
            {
                "cause": "CloudWatch agent service is stopped or failed due to JSON configuration syntax error",
                "likelihood": "common",
                "evidence_needed": "systemctl status amazon-cloudwatch-agent shows inactive or configuration parse error.",
                "remediation": "Validate `/opt/aws/amazon-cloudwatch-agent/bin/config.json` and start agent service."
            }
        ],
        "investigation_steps": [
            {
                "order": 1,
                "title": "Check CloudWatch Agent Service Status and Logs",
                "command": "sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status && sudo tail -n 25 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log",
                "explanation": "Check if daemon is running and view recent error logs.",
                "what_to_look_for": "status: running vs stopped; look for AccessDenied or config errors."
            }
        ],
        "verification": "CloudWatch Metrics console displays active data points under 'CWAgent' namespace.",
        "prevention": [
            "Automate CloudWatch agent installation and configuration via AWS Systems Manager State Manager."
        ],
        "references": [
            "https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/troubleshooting-CloudWatch-Agent.html"
        ]
    }
]

for s in SCENARIOS:
    path = CATALOG_DIR / f"{s['id']}.json"
    path.write_text(json.dumps(s, indent=2), encoding="utf-8")

print(f"Successfully generated {len(SCENARIOS)} scenario files in {CATALOG_DIR}")
