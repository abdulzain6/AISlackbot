FROM python:3.12-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    graphviz \
    && apt-get clean

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all other files
COPY . .

# Make the start.sh script executable
RUN chmod +x start.sh

# Run the start.sh script
CMD ["./start.sh"]