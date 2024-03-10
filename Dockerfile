# Use the official Python base image with version 3.10
FROM python:3.10

# Set the working directory inside the container
WORKDIR /app

# Copy the static HTML files to the working directory
COPY html /app/html

# Install the pip dependencies
RUN pip install pywebhost coloredlogs

# Copy the application code to the working directory
COPY chatroom.py .

# Expose port 3300 for the application
EXPOSE 3300

# Set the entrypoint command to run the Python application
CMD ["python", "chatroom.py","3300","no-interact"]
