FROM python:3.9

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install pip and dependencies from requirements.txt
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install the latest yt-dlp
RUN pip install --upgrade yt-dlp

# Expose the port
EXPOSE 80

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:80", "app:app"]
