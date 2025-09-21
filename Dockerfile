FROM python:3.13-bookworm

# Install system dependencies required for building some Python packages.
# `build-essential` includes compilers, `libffi-dev` and `libssl-dev` are common for network-related packages.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        # Add any other system dependencies your specific Python packages might need.
    && rm -rf /var/lib/apt/lists/*

# Install uv by copying its binaries from a dedicated uv image.
# This ensures you get a specific, tested version of uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory inside the container.
WORKDIR /app

# Copy your application code and uv project files into the container.
# This assumes your main Python file is in the root of your project context.
COPY . /app

# Ensure that uv can find its binaries by adding them to the PATH.
ENV PATH="/bin:${PATH}"

# Create the virtual environment explicitly
RUN python -m venv /app/.venv

# Ensure the Class directory exists and has the __init__.py file
RUN touch /app/Class/__init__.py

# Activate the virtual environment and then run uv sync
RUN . /app/.venv/bin/activate && uv sync

# Set PYTHONPATH to include the app directory so Class module can be imported
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Ensure the Class directory is properly accessible
RUN ls -la /app/Class/

# Cloud Run services listen on the port specified by the PORT environment variable.
# Expose this port so Docker knows your application listens on it.
EXPOSE $PORT

# Command to run your application.
# Set PYTHONPATH to ensure module imports work correctly in the container
CMD ["sh", "-c", "PYTHONPATH=/app uv run mcp_app.py --host 0.0.0.0 --port 8080"]
