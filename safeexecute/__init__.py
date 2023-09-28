import os
import re
import logging
import subprocess
import docker
from docker.errors import ImageNotFound


async def execute_python_code(self, code: str, working_directory: str) -> str:
    # Check if there are any package requirements in the code to install
    package_requirements = re.findall(r"pip install (.*)", code)
    if package_requirements:
        # Install the required packages
        for package in package_requirements:
            try:
                subprocess.check_output(["pip", "install", package])
            except:
                pass
    code = await self.get_python_code_from_response(code)
    # Create a temporary Python file in the WORKSPACE directory
    temp_file = os.path.join(working_directory, "temp.py")
    with open(temp_file, "w") as f:
        f.write(code)
    try:
        client = docker.from_env()
        image_name = "joshxt/safeexecute:latest"
        try:
            client.images.get(image_name)
            logging.info(f"Image '{image_name}' found locally")
        except ImageNotFound:
            logging.info(
                f"Image '{image_name}' not found locally, pulling from Docker Hub"
            )
            low_level_client = docker.APIClient()
            for line in low_level_client.pull(image_name, stream=True, decode=True):
                status = line.get("status")
                progress = line.get("progress")
                if status and progress:
                    logging.info(f"{status}: {progress}")
                elif status:
                    logging.info(status)
        container = client.containers.run(
            image_name,
            f"python {temp_file}",
            volumes={
                os.path.abspath(working_directory): {
                    "bind": "/workspace",
                    "mode": "ro",
                }
            },
            working_dir="/workspace",
            stderr=True,
            stdout=True,
            detach=True,
        )
        container.wait()
        logs = container.logs().decode("utf-8")
        container.remove()
        os.remove(temp_file)
        return logs
    except Exception as e:
        return f"Error: {str(e)}"
