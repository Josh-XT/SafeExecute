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
    import json
    import re
    import threading
    import glob

    def parse_tool_calls_from_logs(
        log_dir: str, last_position: dict, stream_callback
    ) -> None:
        """Parse log files for tool calls and stream them."""
        if not stream_callback or not os.path.exists(log_dir):
            return

        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        for log_file in log_files:
            try:
                file_key = os.path.basename(log_file)
                if file_key not in last_position:
                    last_position[file_key] = 0

                with open(log_file, "r") as f:
                    f.seek(last_position[file_key])
                    new_content = f.read()
                    last_position[file_key] = f.tell()

                if not new_content:
                    continue

                # Parse tool calls from the log content
                # Look for tool_calls in JSON responses
                tool_call_pattern = r'"tool_calls":\s*\[(.*?)\]'
                for match in re.finditer(tool_call_pattern, new_content, re.DOTALL):
                    try:
                        tool_calls_str = "[" + match.group(1) + "]"
                        # Clean up the JSON
                        tool_calls_str = re.sub(r"\s+", " ", tool_calls_str)
                        tool_calls = json.loads(tool_calls_str)

                        for tool_call in tool_calls:
                            func = tool_call.get("function", {})
                            func_name = func.get("name", "unknown")
                            func_args_str = func.get("arguments", "{}")

                            try:
                                func_args = json.loads(func_args_str)
                            except:
                                func_args = {"raw": func_args_str}

                            # Format the tool call for display
                            if func_name == "bash":
                                cmd = func_args.get("command", "")
                                desc = func_args.get("description", "Running command")
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"\n🖥️ **{desc}**\n```bash\n{cmd}\n```",
                                    }
                                )
                            elif func_name == "stop_bash":
                                # Stopping a running command
                                stream_callback(
                                    {
                                        "type": "tool_complete",
                                        "content": f"\n⏹️ **Stopped command**",
                                    }
                                )
                            elif func_name == "view" or func_name == "read_file":
                                path = func_args.get(
                                    "path", func_args.get("file_path", "")
                                )
                                start = func_args.get("start_line", "")
                                end = func_args.get("end_line", "")
                                line_info = f" (lines {start}-{end})" if start else ""
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"📄 **Read**: `{path}`{line_info}",
                                    }
                                )
                            elif (
                                func_name == "write_file"
                                or func_name == "edit_file"
                                or func_name == "edit"
                            ):
                                path = func_args.get(
                                    "path", func_args.get("file_path", "")
                                )
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"✏️ **Write**: `{path}`",
                                    }
                                )
                            elif func_name == "report_intent":
                                intent = func_args.get("intent", "")
                                stream_callback(
                                    {
                                        "type": "thinking",
                                        "content": f"\n💭 **Intent**: {intent}",
                                    }
                                )
                            elif func_name == "glob" or func_name == "find_files":
                                pattern = func_args.get(
                                    "pattern", func_args.get("glob", "")
                                )
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"🔍 **Find files**: `{pattern}`",
                                    }
                                )
                            elif func_name == "grep" or func_name == "search":
                                pattern = func_args.get(
                                    "pattern", func_args.get("query", "")
                                )
                                path = func_args.get(
                                    "path", func_args.get("directory", ".")
                                )
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"🔎 **Search**: `{pattern}` in `{path}`",
                                    }
                                )
                            elif func_name == "ls" or func_name == "list":
                                path = func_args.get(
                                    "path", func_args.get("directory", ".")
                                )
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"📁 **List**: `{path}`",
                                    }
                                )
                            elif "github-mcp-server" in func_name:
                                # GitHub MCP tools - format nicely
                                tool_short = (
                                    func_name.replace("github-mcp-server-", "")
                                    .replace("_", " ")
                                    .title()
                                )
                                # Extract key info based on tool type
                                if "clone" in func_name.lower():
                                    repo = func_args.get(
                                        "repository", func_args.get("repo", "")
                                    )
                                    stream_callback(
                                        {
                                            "type": "tool_start",
                                            "content": f"\n🔄 **Clone Repository**: `{repo}`",
                                        }
                                    )
                                elif "create_pull_request" in func_name.lower():
                                    title = func_args.get("title", "")
                                    stream_callback(
                                        {
                                            "type": "tool_start",
                                            "content": f"📝 **Create Pull Request**: {title}",
                                        }
                                    )
                                elif "commit" in func_name.lower():
                                    msg = func_args.get("message", "")[:100]
                                    stream_callback(
                                        {
                                            "type": "tool_start",
                                            "content": f"💾 **Commit**: {msg}",
                                        }
                                    )
                                elif "push" in func_name.lower():
                                    branch = func_args.get("branch", "")
                                    stream_callback(
                                        {
                                            "type": "tool_start",
                                            "content": f"⬆️ **Push**: `{branch}`",
                                        }
                                    )
                                else:
                                    stream_callback(
                                        {
                                            "type": "tool_start",
                                            "content": f"\n🔧 **{tool_short}**",
                                        }
                                    )
                            elif func_name == "wait_for_user":
                                # Waiting for user input
                                stream_callback(
                                    {
                                        "type": "thinking",
                                        "content": f"\n⏳ **Waiting for input**",
                                    }
                                )
                            elif (
                                func_name == "task_complete" or func_name == "complete"
                            ):
                                # Task completed
                                stream_callback(
                                    {
                                        "type": "tool_complete",
                                        "content": f"\n✅ **Task completed**",
                                    }
                                )
                            else:
                                # Generic tool - show name with gear icon and brief args
                                args_brief = json.dumps(func_args)[:100]
                                if len(args_brief) >= 100:
                                    args_brief = args_brief[:97] + "..."
                                # Format tool name nicely
                                nice_name = func_name.replace("_", " ").title()
                                stream_callback(
                                    {
                                        "type": "tool_start",
                                        "content": f"\n⚙️ **{nice_name}**\n{args_brief}",
                                    }
                                )
                    except json.JSONDecodeError:
                        pass  # Skip malformed JSON

            except Exception as e:
                logging.debug(f"Error parsing log file {log_file}: {e}")

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
                    "content": f"🚀 **Starting GitHub Copilot** with model `{model}`\n",
                }
            )

        # Write prompt to a temp file to avoid shell escaping issues
        prompt_file = os.path.join(working_directory, ".copilot_prompt.txt")
        with open(prompt_file, "w") as f:
            f.write(prompt)

        # Session file for capturing session ID
        session_file = "/workspace/.copilot_session.md"

        # Log directory for capturing tool calls
        log_dir = "/workspace/.copilot_logs"

        # Build command that reads from the prompt file and exports session
        # Use --stream on to enable streaming output for better real-time feedback
        # Use --log-level debug to capture tool calls in log files
        cmd = f'mkdir -p {log_dir} && copilot -p "$(cat /workspace/.copilot_prompt.txt)" --model {model} --allow-all --no-auto-update --stream on --log-level debug --log-dir {log_dir} --share {session_file}'
        if session_id:
            cmd += f" --resume {session_id}"

        # Create a persistent config directory for Copilot sessions
        # This allows session resumption across container runs
        copilot_config_dir = os.path.join(working_directory, ".copilot_config")
        if not os.path.exists(copilot_config_dir):
            os.makedirs(copilot_config_dir)

        # Use stdbuf to disable output buffering for real-time streaming
        # This ensures copilot output is flushed immediately
        unbuffered_cmd = f"stdbuf -oL -eL {cmd}"

        # Run the CLI in the container with pseudo-TTY for streaming
        container = client.containers.run(
            IMAGE_NAME,
            ["bash", "-c", unbuffered_cmd],
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
                # Force unbuffered Python output if copilot uses Python
                "PYTHONUNBUFFERED": "1",
            },
            stderr=True,
            stdout=True,
            detach=True,
            tty=True,  # Enable TTY for streaming output
        )

        # Collect output and buffer for line-based streaming
        all_output = []
        line_buffer = ""
        last_emit_time = 0
        import time

        def emit_buffered_content(content: str, force: bool = False):
            """Emit buffered content as appropriate event types."""
            nonlocal last_emit_time
            if not stream_callback or not content.strip():
                return

            current_time = time.time()
            # Rate limit to avoid spamming - emit at most every 0.1 seconds unless forced
            if not force and (current_time - last_emit_time) < 0.1:
                return

            stripped = content.strip()
            if not stripped:
                return

            last_emit_time = current_time

            # Skip stats and metadata lines
            if any(
                stripped.startswith(s)
                for s in ["Total ", "Usage by", "Session exported"]
            ):
                return

            lower_content = stripped.lower()

            # Patterns that should have a line break BEFORE them (major transitions)
            linebreak_before_patterns = [
                "cloning",
                "clone ",
                "intent:",
                "i'll clone",
                "let me clone",
                "i'll start by",
                "first, i'll",
                "i will ",
                "let me ",
                "now i'll",
                "next, i'll",
                "analyzing",
                "examining",
            ]

            # Check if we need a line break before this content
            needs_linebreak = any(
                pattern in lower_content for pattern in linebreak_before_patterns
            )
            prefix = "\n" if needs_linebreak else ""

            # Detect tool execution patterns - starting an operation
            tool_start_patterns = [
                "reading file",
                "reading `",
                "writing file",
                "writing to",
                "creating file",
                "creating `",
                "modifying",
                "deleting",
                "searching",
                "running command",
                "executing",
                "checking",
                "analyzing",
                "scanning",
                "cloning",
                "fetching",
                "pulling",
                "pushing",
                "committing",
                "staging",
                "looking at",
                "examining",
                "inspecting",
                "opening",
                "loading",
                "parsing",
                "processing",
                "building",
                "compiling",
                "installing",
                "downloading",
                "git clone",
                "git pull",
                "git push",
                "git checkout",
                "npm install",
                "pip install",
                "cargo build",
            ]

            # Detect tool completion patterns - these get a newline before them
            tool_complete_patterns = [
                "created `",
                "wrote to",
                "modified `",
                "deleted",
                "found",
                "completed",
                "successfully",
                "done",
                "finished",
                "updated `",
                "cloned",
                "fetched",
                "pulled",
                "pushed",
                "committed",
                "installed",
                "downloaded",
                "built",
                "compiled",
                "here's",
                "here is",
                "i've ",
                "i have ",
            ]

            # Detect intent/thinking patterns
            intent_patterns = [
                "let me ",
                "i'll ",
                "i will ",
                "now i",
                "first,",
                "next,",
                "intent:",
                "plan:",
                "approach:",
            ]

            if any(pattern in lower_content for pattern in tool_start_patterns):
                stream_callback(
                    {"type": "tool_start", "content": f"{prefix}{stripped}"}
                )
            elif any(pattern in lower_content for pattern in tool_complete_patterns):
                # Tool completions get a newline before them for visual separation
                stream_callback({"type": "tool_complete", "content": f"\n{stripped}"})
            elif stripped.lower().startswith("error") or "error:" in lower_content:
                stream_callback({"type": "error", "content": stripped})
            elif any(pattern in lower_content for pattern in intent_patterns):
                stream_callback(
                    {"type": "thinking", "content": f"{prefix}💭 {stripped}"}
                )
            else:
                # Stream as thinking for all other meaningful content
                stream_callback({"type": "thinking", "content": stripped})

        try:
            # Use attach with a socket for true real-time streaming
            # The logs() API buffers when TTY is enabled
            socket = container.attach_socket(
                params={"stdout": True, "stderr": True, "stream": True}
            )
            socket._sock.setblocking(False)

            import select
            import time as time_module

            start_time = time_module.time()
            timeout = 3600  # 1 hour max

            # Track log file positions for incremental reading
            log_positions = {}
            copilot_log_dir = os.path.join(working_directory, ".copilot_logs")
            last_log_check = 0

            while True:
                # Check if container is still running
                container.reload()
                if container.status != "running":
                    # Get any remaining output
                    try:
                        while True:
                            ready, _, _ = select.select([socket._sock], [], [], 0.1)
                            if ready:
                                data = socket._sock.recv(4096)
                                if data:
                                    chunk_str = data.decode("utf-8", errors="replace")
                                    all_output.append(chunk_str)
                                    line_buffer += chunk_str
                                    while "\n" in line_buffer or "\r" in line_buffer:
                                        if "\n" in line_buffer:
                                            line, line_buffer = line_buffer.split(
                                                "\n", 1
                                            )
                                        else:
                                            line, line_buffer = line_buffer.split(
                                                "\r", 1
                                            )
                                        emit_buffered_content(line, force=True)
                                else:
                                    break
                            else:
                                break
                    except:
                        pass
                    # Final log parse
                    parse_tool_calls_from_logs(
                        copilot_log_dir, log_positions, stream_callback
                    )
                    break

                # Check for timeout
                if time_module.time() - start_time > timeout:
                    logging.warning("Container execution timed out")
                    break

                # Parse log files for tool calls every 0.5 seconds
                current_time = time_module.time()
                if current_time - last_log_check >= 0.5:
                    parse_tool_calls_from_logs(
                        copilot_log_dir, log_positions, stream_callback
                    )
                    last_log_check = current_time

                # Try to read from socket with timeout
                try:
                    ready, _, _ = select.select([socket._sock], [], [], 0.5)
                    if ready:
                        data = socket._sock.recv(4096)
                        if data:
                            chunk_str = data.decode("utf-8", errors="replace")
                            all_output.append(chunk_str)
                            line_buffer += chunk_str

                            # Process complete lines
                            while "\n" in line_buffer or "\r" in line_buffer:
                                if "\n" in line_buffer:
                                    line, line_buffer = line_buffer.split("\n", 1)
                                else:
                                    line, line_buffer = line_buffer.split("\r", 1)
                                emit_buffered_content(line, force=True)

                            # Emit partial content for long buffers
                            if len(line_buffer) > 200:
                                emit_buffered_content(line_buffer)
                except BlockingIOError:
                    pass
                except Exception as e:
                    logging.debug(f"Socket read error: {e}")

            socket.close()

        except Exception as e:
            logging.warning(f"Error streaming logs: {str(e)}")
            # Fallback to logs() if socket approach fails
            try:
                for log_chunk in container.logs(stream=True, follow=True):
                    chunk_str = log_chunk.decode("utf-8", errors="replace")
                    all_output.append(chunk_str)
                    line_buffer += chunk_str
                    while "\n" in line_buffer or "\r" in line_buffer:
                        if "\n" in line_buffer:
                            line, line_buffer = line_buffer.split("\n", 1)
                        else:
                            line, line_buffer = line_buffer.split("\r", 1)
                        emit_buffered_content(line, force=True)
            except Exception as e2:
                logging.warning(f"Fallback streaming also failed: {e2}")

        # Emit any remaining buffered content
        if line_buffer.strip():
            emit_buffered_content(line_buffer, force=True)

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

        # Clean up the log directory
        copilot_log_dir_host = os.path.join(working_directory, ".copilot_logs")
        if os.path.exists(copilot_log_dir_host):
            import shutil

            try:
                shutil.rmtree(copilot_log_dir_host)
            except Exception as e:
                logging.debug(f"Failed to clean up log dir: {e}")

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
