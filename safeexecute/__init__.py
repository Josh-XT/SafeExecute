import os
import re
import logging
import docker

IMAGE_NAME = "joshxt/safeexecute:latest"


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


def execute_python_code(code: str, working_directory: str = None) -> str:
    if working_directory is None:
        working_directory = os.path.join(os.getcwd(), "WORKSPACE")
    if not os.path.exists(working_directory):
        os.makedirs(working_directory)
    # Check if there are any package requirements in the code to install
    package_requirements = re.findall(r"pip install (.*)", code)
    # Strip out python code blocks if they exist in the code
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    temp_file = os.path.join(working_directory, "temp.py")
    with open(temp_file, "w") as f:
        f.write(code)
    os.chmod(temp_file, 0o755)  # Set executable permissions
    try:
        client = install_docker_image()
        if package_requirements:
            # Install the required packages in the container
            for package in package_requirements:
                try:
                    logging.info(f"Installing package '{package}' in container")
                    client.containers.run(
                        IMAGE_NAME,
                        f"pip install {package}",
                        volumes={
                            os.path.abspath(working_directory): {
                                "bind": "/workspace",
                                "mode": "rw",
                            }
                        },
                        working_dir="/workspace",
                        stderr=True,
                        stdout=True,
                        detach=True,
                    )
                except Exception as e:
                    logging.error(f"Error installing package '{package}': {str(e)}")
                    return f"Error: {str(e)}"
        # Run the Python code in the container
        container = client.containers.run(
            IMAGE_NAME,
            f"python /workspace/temp.py",
            volumes={
                os.path.abspath(working_directory): {
                    "bind": "/workspace",
                    "mode": "rw",
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
        logging.info(f"Python code executed successfully. Logs: {logs}")
        return logs
    except Exception as e:
        logging.error(f"Error executing Python code: {str(e)}")
        return f"Error: {str(e)}"


if __name__ == "__main__":
    install_docker_image()
