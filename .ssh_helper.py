"""SSH helper for reading server logs."""
import paramiko

HOST = "80.78.253.76"
USER = "cursor_ro"
PASS = "cursorRO2026"

def run(cmd: str) -> str:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=15)
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    ssh.close()
    return out + (("\nSTDERR: " + err) if err.strip() else "")

if __name__ == "__main__":
    import sys
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "docker ps"
    print(run(cmd))
