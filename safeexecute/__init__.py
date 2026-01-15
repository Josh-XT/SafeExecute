import os
import re
import ast
import json
import logging
import docker
import asyncio
from typing import Optional, Dict, Any, Callable

IMAGE_NAME = "joshxt/safeexecute:latest"

# Common import name to package name mappings
IMPORT_TO_PACKAGE = {
    "cv2": "opencv-python",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "Bio": "biopython",
    "cv": "opencv-python",
    "telegram": "python-telegram-bot",
    "serial": "pyserial",
    "usb": "pyusb",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyopenssl",
    "jwt": "pyjwt",
    "wx": "wxpython",
    "gi": "pygobject",
    "fitz": "pymupdf",
    "lxml": "lxml",
    "openpyxl": "openpyxl",
    "xlrd": "xlrd",
    "xlsxwriter": "xlsxwriter",
}


def install_docker_image():
    client = docker.from_env()
    try:
        client.images.get(IMAGE_NAME)
        logging.info(f"Image '{IMAGE_NAME}' found locally")
    except:
        logging.info(f"Installing docker image '{IMAGE_NAME}' from Docker Hub")
        client.images.pull(IMAGE_NAME)
        logging.info(f"Image '{IMAGE_NAME}' installed")
    return client


def extract_imports(code: str) -> set:
    """Extract all imported module names from Python code."""
    imports = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Get the top-level module name
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    except SyntaxError:
        # Fallback to regex if AST parsing fails
        import_pattern = r"^\s*(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(import_pattern, code, re.MULTILINE):
            imports.add(match.group(1))
    return imports


def execute_python_code(code: str, working_directory: str = None) -> str:
    if working_directory is None:
        working_directory = os.path.join(os.getcwd(), "WORKSPACE")

    # When in Docker, translate container path to host path for volume mounting
    docker_volume_path = working_directory
    if os.path.exists("/.dockerenv"):
        host_workspace = os.environ.get("WORKING_DIRECTORY")
        if host_workspace:
            # Extract relative path after /WORKSPACE and append to host path
            workspace_marker = "/WORKSPACE"
            if workspace_marker in working_directory:
                relative_part = working_directory.split(workspace_marker, 1)[1]
                docker_volume_path = host_workspace.rstrip("/") + relative_part
            else:
                docker_volume_path = host_workspace

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    # Check if there are any explicit pip install commands in the code
    explicit_packages = re.findall(r"pip install\s+([\w\-\[\]>=<,.\s]+)", code)
    explicit_packages = [p.strip() for p in explicit_packages if p.strip()]

    # Strip out python code blocks if they exist in the code
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]

    # Extract imports from the code to auto-install missing packages
    imports = extract_imports(code)

    temp_file = os.path.join(working_directory, "temp.py")
    with open(temp_file, "w") as f:
        f.write(code)
    os.chmod(temp_file, 0o755)  # Set executable permissions

    try:
        client = install_docker_image()

        # Build a wrapper script that installs missing packages then runs the code
        # This ensures packages are installed in the SAME container that runs the code
        install_commands = []

        # Add explicit pip install packages
        for pkg in explicit_packages:
            install_commands.append(f"pip install -q {pkg} 2>/dev/null || true")

        # Map imports to package names and install them
        for imp in imports:
            pkg_name = IMPORT_TO_PACKAGE.get(imp, imp)
            install_commands.append(
                f"python -c 'import {imp}' 2>/dev/null || pip install -q {pkg_name} 2>/dev/null || true"
            )

        # Create a wrapper script that installs deps then runs the code
        install_script = "\n".join(install_commands)
        wrapper_script = f"""#!/bin/bash
{install_script}
python /workspace/temp.py
"""
        wrapper_file = os.path.join(working_directory, "run_wrapper.sh")
        with open(wrapper_file, "w") as f:
            f.write(wrapper_script)
        os.chmod(wrapper_file, 0o755)

        # Run the wrapper script in the container
        container = client.containers.run(
            IMAGE_NAME,
            f"bash /workspace/run_wrapper.sh",
            volumes={
                os.path.abspath(docker_volume_path): {
                    "bind": "/workspace",
                    "mode": "rw",
                }
            },
            working_dir="/workspace",
            stderr=True,
            stdout=True,
            detach=True,
        )
        result = container.wait()
        exit_code = result.get("StatusCode", 0)
        logs = container.logs().decode("utf-8")
        container.remove()

        # Clean up temp files
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(wrapper_file):
            os.remove(wrapper_file)

        # Check for errors in output and add guidance for the AI
        error_indicators = [
            "Traceback (most recent call last):",
            "SyntaxError:",
            "NameError:",
            "TypeError:",
            "ValueError:",
            "KeyError:",
            "IndexError:",
            "AttributeError:",
            "ImportError:",
            "ModuleNotFoundError:",
            "FileNotFoundError:",
            "ZeroDivisionError:",
            "RuntimeError:",
            "Exception:",
        ]

        has_error = exit_code != 0 or any(
            indicator in logs for indicator in error_indicators
        )

        if has_error:
            logging.warning(f"Python code execution had errors. Logs: {logs}")
            guidance = (
                "\n\n---\n"
                "**Code Execution Failed**: The code above produced an error. "
                "Please analyze the error message, fix the code, and try again. "
                "Common fixes include:\n"
                "- Check column names match exactly (use df.columns to see available columns)\n"
                "- Verify file paths and filenames exist\n"
                "- Ensure required variables are defined before use\n"
                "- Check data types match expected operations\n"
                "- Handle missing or null values appropriately\n"
            )
            return logs + guidance
        else:
            logging.info(f"Python code executed successfully. Logs: {logs}")
            return logs
    except Exception as e:
        logging.error(f"Error executing Python code: {str(e)}")
        return f"Error: {str(e)}\n\n---\n**Execution Failed**: Please fix the issue and try again."


def execute_github_copilot(
    prompt: str,
    github_token: str,
    working_directory: str = None,
    model: str = "claude-opus-4.5",
    session_id: str = None,
    stream_callback: callable = None,
) -> dict:
    """
    Execute a prompt using GitHub Copilot CLI within a Docker container.

    The GitHub Copilot CLI is an agentic coding assistant that can read, modify,
    and create files in the working directory. It runs in a secure container
    environment with the workspace mounted.

    IMPORTANT: The GitHub Copilot CLI requires a **fine-grained** Personal Access Token
    (starts with 'github_pat_'). Classic PATs (starting with 'ghp_') are NOT supported.

    Args:
        prompt: The prompt/request to send to GitHub Copilot
        github_token: Fine-grained GitHub PAT (github_pat_...) with "Copilot" account permission
        working_directory: The directory to mount as the workspace (default: WORKSPACE)
        model: The model to use (default: claude-opus-4.5). Options: claude-opus-4.5,
               claude-sonnet-4, gpt-4.1, gpt-5, gpt-5-mini
        session_id: Optional session ID to resume an existing session. If provided,
                    Copilot will continue from where the previous session left off.
        stream_callback: Optional callback function that receives streaming events.
                         The callback receives a dict with 'type' and 'content' keys.
                         Event types: 'output', 'error', 'complete'

    Returns:
        dict: A dictionary containing:
            - 'response': The final response from GitHub Copilot
            - 'session_id': The session ID (can be used to resume this session)
            - 'success': Boolean indicating if the operation was successful
    """
    # Validate token format - Copilot CLI does NOT support classic PATs
    if github_token and github_token.startswith("ghp_"):
        error_msg = (
            "Classic Personal Access Tokens (ghp_...) are NOT supported by GitHub Copilot CLI.\n\n"
            "You must use a **fine-grained** PAT (starting with 'github_pat_').\n\n"
            "To create a compatible token:\n"
            "1. Visit https://github.com/settings/personal-access-tokens/new\n"
            "2. Give your token a name and set an expiration\n"
            "3. Under 'Repository access', select repos Copilot can access\n"
            "4. Under 'Account permissions', find 'Copilot' and select 'Read and write'\n"
            "5. Generate and use the new token (starts with 'github_pat_')"
        )
        if stream_callback:
            stream_callback({"type": "error", "content": error_msg})
        return {
            "response": f"Error: {error_msg}",
            "session_id": None,
            "success": False,
        }

    if working_directory is None:
        working_directory = os.path.join(os.getcwd(), "WORKSPACE")

    # Handle Docker-in-Docker path translation
    docker_volume_path = working_directory
    if os.path.exists("/.dockerenv"):
        host_workspace = os.environ.get("WORKING_DIRECTORY")
        if host_workspace:
            workspace_marker = "/WORKSPACE"
            if workspace_marker in working_directory:
                relative_part = working_directory.split(workspace_marker, 1)[1]
                docker_volume_path = host_workspace.rstrip("/") + relative_part
            else:
                docker_volume_path = host_workspace

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    try:
        client = install_docker_image()

        # Build the copilot CLI command
        # Use -p for non-interactive prompt mode with --allow-all for full permissions
        cmd_parts = [
            "copilot",
            "-p",
            prompt,
            "--model",
            model,
            "--allow-all",  # Allow all tools, paths, and URLs
            "--no-auto-update",  # Don't check for updates
        ]

        # Add session resume if provided
        if session_id:
            cmd_parts.extend(["--resume", session_id])

        if stream_callback:
            stream_callback(
                {
                    "type": "info",
                    "content": f"Starting GitHub Copilot with model {model}...",
                }
            )

        # Write prompt to a temp file to avoid shell escaping issues
        prompt_file = os.path.join(working_directory, ".copilot_prompt.txt")
        with open(prompt_file, "w") as f:
            f.write(prompt)

        # Session file for capturing session ID
        session_file = "/workspace/.copilot_session.md"

        # Build command that reads from the prompt file and exports session
        cmd = f'copilot -p "$(cat /workspace/.copilot_prompt.txt)" --model {model} --allow-all --no-auto-update --share {session_file}'
        if session_id:
            cmd += f" --resume {session_id}"

        # Create a persistent config directory for Copilot sessions
        # This allows session resumption across container runs
        copilot_config_dir = os.path.join(working_directory, ".copilot_config")
        if not os.path.exists(copilot_config_dir):
            os.makedirs(copilot_config_dir)

        # Run the CLI in the container
        container = client.containers.run(
            IMAGE_NAME,
            ["bash", "-c", cmd],
            volumes={
                os.path.abspath(docker_volume_path): {
                    "bind": "/workspace",
                    "mode": "rw",
                },
                os.path.abspath(copilot_config_dir): {
                    "bind": "/root/.copilot",
                    "mode": "rw",
                },
            },
            working_dir="/workspace",
            environment={
                "HOME": "/root",
                "GITHUB_TOKEN": github_token,
                "GH_TOKEN": github_token,
                "COPILOT_GITHUB_TOKEN": github_token,
            },
            stderr=True,
            stdout=True,
            detach=True,
        )

        # Collect output
        all_output = []

        try:
            # Stream the container logs in real-time
            for log_chunk in container.logs(stream=True, follow=True):
                log_line = log_chunk.decode("utf-8")
                all_output.append(log_line)

                if stream_callback:
                    stream_callback({"type": "output", "content": log_line})

        except Exception as e:
            logging.warning(f"Error streaming logs: {str(e)}")

        # Wait for container to finish
        try:
            wait_result = container.wait(timeout=3630)  # 60 minutes + 30 seconds buffer
            exit_code = wait_result.get("StatusCode", 0)
        except Exception as e:
            logging.warning(f"Container wait timeout: {str(e)}")
            exit_code = 1

        container.remove(force=True)

        # Clean up the prompt file
        if os.path.exists(prompt_file):
            os.remove(prompt_file)

        # Parse session ID from the session markdown file
        session_md_path = os.path.join(working_directory, ".copilot_session.md")
        result_session_id = session_id  # Default to the input session_id
        if os.path.exists(session_md_path):
            try:
                with open(session_md_path, "r") as f:
                    session_content = f.read()
                # Look for session ID pattern: > **Session ID:** `uuid`
                import re

                session_match = re.search(
                    r"\*\*Session ID:\*\*\s*`([a-f0-9-]+)`", session_content
                )
                if session_match:
                    result_session_id = session_match.group(1)
                os.remove(session_md_path)
            except Exception as e:
                logging.warning(f"Error parsing session file: {str(e)}")

        # Parse the output
        full_output = "".join(all_output)

        # Extract response (everything before the stats section)
        response_lines = []
        in_stats = False
        for line in full_output.split("\n"):
            # Stats section starts with "Total usage est:" or similar
            if line.strip().startswith("Total usage est:") or line.strip().startswith(
                "Total duration"
            ):
                in_stats = True
            if not in_stats:
                response_lines.append(line)

        response_text = "\n".join(response_lines).strip()

        if exit_code != 0:
            logging.warning(
                f"GitHub Copilot execution had errors. Exit code: {exit_code}"
            )
            # Check for common error patterns
            if "No authentication information found" in full_output:
                response_text = (
                    "Authentication failed. Please ensure your token:\n"
                    "1. Is a fine-grained PAT (starts with 'github_pat_')\n"
                    "2. Has the 'Copilot' account permission enabled\n"
                    "3. Has not expired\n\n"
                    f"Raw output: {full_output}"
                )
            return {
                "response": response_text or full_output,
                "session_id": result_session_id,
                "success": False,
            }

        if stream_callback:
            stream_callback(
                {"type": "complete", "content": "GitHub Copilot completed successfully"}
            )

        logging.info("GitHub Copilot executed successfully")
        return {
            "response": response_text,
            "session_id": result_session_id,
            "success": True,
        }

    except Exception as e:
        logging.error(f"Error executing GitHub Copilot: {str(e)}")
        return {
            "response": f"Error running GitHub Copilot: {str(e)}",
            "session_id": session_id,
            "success": False,
        }


if __name__ == "__main__":
    install_docker_image()
