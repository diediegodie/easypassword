#!/bin/sh

# Exit on error
set -e

echo "Starting EasyPassword backend initialization..."

# Wait for database with retries using simple connection attempt
wait_for_db() {
    echo "Waiting for PostgreSQL to be ready..."
    max_attempts=30
    attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if alembic current > /dev/null 2>&1; then
            echo "✓ Database is ready!"
            return 0
        fi
        
        attempt=$((attempt + 1))
        echo "  [$attempt/$max_attempts] Database not ready, retrying in 2 seconds..."
        sleep 2
    done
    
    echo "✗ ERROR: Database did not become ready after $max_attempts attempts"
    exit 1
}

# Function to run migrations
run_migrations() {
    echo ""
    echo "Running database migrations..."
    alembic upgrade head
    echo "✓ Migrations completed successfully!"
    echo ""
}

# Execute initialization steps
wait_for_db
run_migrations

# Start the application
echo "Starting EasyPassword API on http://0.0.0.0:8000"
exec uvicorn main:app --host 0.0.0.0 --port 8000
