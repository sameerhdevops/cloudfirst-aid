# Runbook: SSH Permission Denied (publickey) (CFA-002)

## 1. Problem
A developer reports:
> "I can ping our EC2 instance, and SSH connects instantly, but I am rejected with 'Permission denied (publickey)'. I am using the PEM key that was downloaded from the AWS console."

## 2. What the Engineer Sees
```text
$ ssh -i my-project-key.pem ec2-user@203.0.113.50
ec2-user@203.0.113.50: Permission denied (publickey,gssapi-keyex,gssapi-with-mic).
```
Running in verbose mode (`ssh -v`):
```text
debug1: Offering public key: my-project-key.pem RSA SHA256:... explicit
debug1: Authentications that can continue: publickey,gssapi-keyex,gssapi-with-mic
debug1: Next authentication method: publickey
debug1: Trying private key: my-project-key.pem
debug1: Server accepts key: no
```

## 3. Before Changing Anything
1. **Notice the TCP connection completed:** The network, Security Group, Route Table, and NACL are 100% functional. Do not waste time debugging VPC networking or Security Groups.
2. Verify the **exact operating system (AMI)** of the EC2 instance. Different Linux distributions define different default login users.
3. Check the **local private key permissions**. OpenSSH clients will refuse to offer private keys that are readable by other local OS users.

## 4. Investigation Sequence

### Step 1: Verify the Default AMI Username
- **Why it matters:** Attempting to log into an Ubuntu instance with `ec2-user` or an Amazon Linux instance with `ubuntu` results in `Permission denied (publickey)`.
- **Command:**
  ```bash
  aws ec2 describe-instances \
    --instance-ids i-0123456789abcdef0 \
    --query "Reservations[*].Instances[*].[ImageId,PlatformDetails]" \
    --output table
  ```
- **Standard Default Usernames:**
  - Amazon Linux 2 / AL2023: `ec2-user`
  - Ubuntu Linux: `ubuntu`
  - Debian: `admin`
  - CentOS: `centos`
  - Red Hat Enterprise Linux (RHEL): `ec2-user`
  - SUSE Linux: `ec2-user`
  - Bitnami: `bitnami`

### Step 2: Check Local Private Key File Permissions
- **Why it matters:** OpenSSH client requires private key files (`.pem`, `id_rsa`) to be readable only by the current owner. If permissions are too open, SSH ignores the key or aborts.
- **On Linux/macOS:**
  ```bash
  ls -l my-project-key.pem
  # Must be -rw------- (0600) or -r-------- (0400)
  ```
- **On Windows (PowerShell):**
  Check ACLs:
  ```powershell
  Get-Acl my-project-key.pem | Format-List
  ```

### Step 3: Match Instance KeyPairName with Local Key
- **Why it matters:** The EC2 console associates an instance with a specific named Key Pair at launch. If you use a different `.pem` file, authentication fails.
- **Command:**
  ```bash
  aws ec2 describe-instances \
    --instance-ids i-0123456789abcdef0 \
    --query "Reservations[*].Instances[*].KeyName" \
    --output text
  ```
- **Interpretation:** Ensure the KeyName matches your local key file name or its registered fingerprint.

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Wrong default username for AMI | **High** | Connecting as `ec2-user` on an Ubuntu instance. |
| Insecure local key permissions | **High** | SSH prints `UNPROTECTED PRIVATE KEY FILE!` warning. |
| Key pair mismatch | **Medium** | AWS KeyName differs from the private key used. |
| Server-side `.ssh/authorized_keys` corrupted or wrong permissions | **Low** | Requires AWS Systems Manager or serial console to inspect. |

## 6. Remediation

### If Username Was Incorrect:
Reconnect using the appropriate username:
```bash
# For Ubuntu:
ssh -i my-project-key.pem ubuntu@203.0.113.50

# For Amazon Linux / RHEL:
ssh -i my-project-key.pem ec2-user@203.0.113.50
```

### If Key Permissions Were Too Open:
- **On Linux / macOS:**
  ```bash
  chmod 400 my-project-key.pem
  ```
- **On Windows (PowerShell):**
  ```powershell
  icacls.exe my-project-key.pem /reset
  icacls.exe my-project-key.pem /inheritance:r
  icacls.exe my-project-key.pem /grant:r "$($env:USERNAME):(R)"
  ```

## 7. Verification
Run SSH:
```bash
ssh -i my-project-key.pem <correct-user>@203.0.113.50
```
Expected output:
```text
Welcome to Ubuntu 22.04.4 LTS (GNU/Linux 6.5.0-1014-aws x86_64)
ubuntu@ip-10-0-1-50:~$
```

## 8. Prevention & Best Practices
1. Use **AWS Systems Manager Session Manager** or **EC2 Instance Connect** for role-based, identity-aware access without static SSH key files.
2. Standardize AMI selection and deployment templates in Terraform / CloudFormation.

## 9. Interview Discussion Points
- **Q: If a user loses their private key, how can they regain access to an EC2 instance?**
  - *Answer:* If AWS Systems Manager (SSM) agent is installed with an attached instance profile, connect via Session Manager and add a new public key to `~/.ssh/authorized_keys`. Alternatively, use EC2 Instance Connect to push a temporary public key via API. If neither is available, stop the instance, detach the EBS root volume, attach it to a helper rescue instance, edit `/home/ec2-user/.ssh/authorized_keys`, and reattach it.

## 10. References
- [AWS EC2: Troubleshooting connecting to your instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html)
- `man 1 ssh`, `man 5 authorized_keys`
