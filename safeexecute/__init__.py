import os
import re
import ast
import logging
import docker

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


if __name__ == "__main__":
    install_docker_image()
