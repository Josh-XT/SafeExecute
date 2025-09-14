import os
import subprocess
import tempfile
import uuid
import logging
import json
import shlex
import re
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)


class BubblewrapSandbox:
    """
    Bubblewrap-based sandbox for code and shell execution
    Works on all cloud platforms without Docker socket
    """

    def __init__(self, workspace_id: str, agent_id: str):
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.workspace_path = os.path.abspath(
            os.path.join(os.getcwd(), "WORKSPACE", agent_id, workspace_id)
        )

        # Ensure workspace exists
        os.makedirs(self.workspace_path, exist_ok=True)

        # Create a state file to track working directory between commands
        self.state_file = os.path.join(self.workspace_path, ".sandbox_state.json")
        self.load_state()

    def load_state(self):
        """Load sandbox state (working directory, env vars, etc.)"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except:
                self.state = {"cwd": "/workspace"}
        else:
            self.state = {"cwd": "/workspace"}

    def save_state(self):
        """Save sandbox state for persistence"""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f)

    def execute_command(
        self, command: str, timeout: int = 30, is_shell: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a command in the sandboxed environment
        Supports both Python code and shell commands
        """

        # Handle cd commands specially to maintain state
        if is_shell and command.strip().startswith("cd "):
            new_dir = command.strip()[3:].strip()
            if new_dir.startswith("/"):
                # Absolute path within sandbox
                self.state["cwd"] = new_dir
            else:
                # Relative path
                self.state["cwd"] = os.path.normpath(
                    os.path.join(self.state["cwd"], new_dir)
                )
            self.save_state()
            return {
                "success": True,
                "stdout": f"Changed directory to {self.state['cwd']}",
                "stderr": "",
                "return_code": 0,
            }

        # Build the bwrap command
        bwrap_cmd = [
            "bwrap",
            # Read-only bind system directories
            "--ro-bind",
            "/usr",
            "/usr",
            # Bind library directories - handle symlinks
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/sbin",
            "/sbin",
            "--ro-bind",
            "/etc/alternatives",
            "/etc/alternatives",
            # SSL certificates for pip
            "--ro-bind",
            "/etc/ssl",
            "/etc/ssl",
            # Bind workspace with write access
            "--bind",
            self.workspace_path,
            "/workspace",
            # Essential virtual filesystems
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            # Networking disabled for security
            "--unshare-net",
            # Process isolation
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            # Die with parent
            "--die-with-parent",
            # Set working directory
            "--chdir",
            self.state["cwd"],
            # Set environment
            "--setenv",
            "HOME",
            "/workspace",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "PYTHONPATH",
            "/workspace",
            # Command to execute
            "--",
        ]

        if is_shell:
            # Execute shell command
            # Wrap in bash to support complex commands
            bwrap_cmd.extend(["/bin/bash", "-c", command])
        else:
            # Execute Python code
            bwrap_cmd.extend(["/usr/bin/python3", "-c", command])

        try:
            # Execute with timeout
            result = subprocess.run(
                bwrap_cmd, capture_output=True, text=True, timeout=timeout
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command timed out",
                "return_code": -1,
            }
        except Exception as e:
            logging.error(f"Bwrap execution error: {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e), "return_code": -1}

    def execute_python_code(self, code: str, timeout: int = 30) -> str:
        """Execute Python code in sandbox"""
        result = self.execute_command(code, timeout, is_shell=False)

        if result["success"]:
            return result["stdout"]
        else:
            return f"Error: {result['stderr']}"

    def execute_shell(self, command: str, timeout: int = 30) -> str:
        """Execute shell command in sandbox"""
        result = self.execute_command(command, timeout, is_shell=True)

        if result["success"]:
            output = result["stdout"]
            if result["stderr"]:
                output += f"\nWarnings: {result['stderr']}"
            return output
        else:
            return f"Error: {result['stderr']}"

    def install_package(self, package: str) -> bool:
        """Install a Python package in the workspace"""
        # Create a virtual environment in the workspace if not exists
        venv_path = os.path.join(self.workspace_path, ".venv")

        if not os.path.exists(venv_path):
            # Create venv (with network for downloads)
            result = self.execute_shell_with_network(
                f"python3 -m venv /workspace/.venv"
            )
            if "Error" in result:
                return False

        # Install package in venv (with network for downloads)
        result = self.execute_shell_with_network(
            f"/workspace/.venv/bin/pip install {package}"
        )
        return "Error" not in result

    def execute_shell_with_network(self, command: str, timeout: int = 60) -> str:
        """Execute shell command with network access (for package installation)"""
        # Build the bwrap command WITH network access
        bwrap_cmd = [
            "bwrap",
            # Read-only bind system directories
            "--ro-bind",
            "/usr",
            "/usr",
            # Bind library directories - handle symlinks
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/sbin",
            "/sbin",
            "--ro-bind",
            "/etc/alternatives",
            "/etc/alternatives",
            # SSL certificates for pip
            "--ro-bind",
            "/etc/ssl",
            "/etc/ssl",
            # DNS resolution
            "--ro-bind",
            "/etc/resolv.conf",
            "/etc/resolv.conf",
            # Bind workspace with write access
            "--bind",
            self.workspace_path,
            "/workspace",
            # Essential virtual filesystems
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            # Process isolation (but NOT network)
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            # Die with parent
            "--die-with-parent",
            # Set working directory
            "--chdir",
            self.state["cwd"],
            # Set environment
            "--setenv",
            "HOME",
            "/workspace",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "PYTHONPATH",
            "/workspace",
            # Command to execute
            "--",
            "/bin/bash",
            "-c",
            command,
        ]

        try:
            result = subprocess.run(
                bwrap_cmd, capture_output=True, text=True, timeout=timeout
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {str(e)}"


# Fallback implementation for when Bubblewrap is not available
class DockerFallback:
    """Fallback to Docker when available (for backward compatibility)"""

    def __init__(self, workspace_id: str, agent_id: str):
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.workspace_path = os.path.join(
            os.getcwd(), "WORKSPACE", agent_id, workspace_id
        )
        os.makedirs(self.workspace_path, exist_ok=True)

    def execute_python_code(self, code: str, timeout: int = 30) -> str:
        """Try to use Docker if available"""
        try:
            import docker

            client = docker.from_env()

            # Write code to temp file
            temp_file = os.path.join(self.workspace_path, "temp.py")
            with open(temp_file, "w") as f:
                f.write(code)

            # Run in Docker container
            container = client.containers.run(
                "python:3.10-slim",
                f"python /workspace/temp.py",
                volumes={
                    os.path.abspath(self.workspace_path): {
                        "bind": "/workspace",
                        "mode": "rw",
                    }
                },
                working_dir="/workspace",
                network_mode="none",
                stderr=True,
                stdout=True,
                detach=True,
                remove=True,
            )

            container.wait(timeout=timeout)
            logs = container.logs().decode("utf-8")

            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)

            return logs

        except Exception as e:
            logging.error(f"Docker execution failed: {str(e)}")
            # Fall back to direct subprocess (unsafe)
            return self._unsafe_execute(code)

    def _unsafe_execute(self, code: str) -> str:
        """Last resort - execute directly (not sandboxed)"""
        logging.warning("WARNING: Executing code without sandbox isolation!")
        try:
            result = subprocess.run(
                ["/usr/bin/python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace_path,
            )
            return (
                result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
            )
        except Exception as e:
            return f"Error: {str(e)}"


# Global instance cache for conversation continuity
_sandbox_cache = {}


def get_sandbox(agent_id: str, conversation_id: str):
    """Get or create sandbox for a conversation"""
    key = f"{agent_id}_{conversation_id}"
    if key not in _sandbox_cache:
        # Check if Bubblewrap is available
        try:
            subprocess.run(["bwrap", "--version"], capture_output=True, check=True)
            _sandbox_cache[key] = BubblewrapSandbox(conversation_id, agent_id)
            logging.info("Using Bubblewrap sandbox")
        except:
            logging.warning("Bubblewrap not available, using fallback")
            _sandbox_cache[key] = DockerFallback(conversation_id, agent_id)

    return _sandbox_cache[key]


# Drop-in replacement functions to maintain compatibility
def execute_python_code(
    code: str,
    working_directory: str = None,
    agent_id: str = None,
    conversation_id: str = None,
) -> str:
    """
    Drop-in replacement for Docker-based safeexecute
    Now uses Bubblewrap for sandboxing when available
    """
    # Handle defaults
    if agent_id is None:
        agent_id = "default"
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    # Clean code blocks if present
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]

    # Get or create sandbox
    sandbox = get_sandbox(agent_id, conversation_id)

    # Check for package installation requests
    packages = re.findall(r"pip install ([^\n]+)", code)
    for package in packages:
        logging.info(f"Installing package: {package}")
        if hasattr(sandbox, "install_package"):
            sandbox.install_package(package.strip())

    # Execute the code
    return sandbox.execute_python_code(code)


def execute_shell_command(
    command: str,
    working_directory: str = None,
    agent_id: str = None,
    conversation_id: str = None,
) -> str:
    """
    Execute shell commands in sandboxed environment
    Maintains working directory state between commands
    """
    # Handle defaults
    if agent_id is None:
        agent_id = "default"
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    # Get or create sandbox
    sandbox = get_sandbox(agent_id, conversation_id)

    # Execute the command
    if hasattr(sandbox, "execute_shell"):
        return sandbox.execute_shell(command)
    else:
        # Fallback doesn't have shell execution
        return "Shell execution not available in fallback mode"


# Compatibility function
def install_docker_image():
    """No-op for compatibility with existing code"""
    logging.info("Checking sandbox availability...")

    # Test that bwrap is available
    try:
        subprocess.run(["bwrap", "--version"], capture_output=True, check=True)
        logging.info("Bubblewrap is available and ready")
    except:
        logging.warning("Bubblewrap not found! Sandbox will use fallback mode")
        logging.info(
            "To enable full sandboxing, install bubblewrap: apt-get install bubblewrap"
        )

    return None


# For backward compatibility
IMAGE_NAME = "joshxt/safeexecute:latest"  # Keep for compatibility


if __name__ == "__main__":
    # Test the sandbox
    install_docker_image()

    # Test Python execution
    result = execute_python_code("print('Hello from sandbox!')")
    print(f"Python test: {result}")

    # Test shell execution
    result = execute_shell_command("echo 'Hello from shell!'")
    print(f"Shell test: {result}")
