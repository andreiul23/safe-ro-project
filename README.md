# SAFE-RO Project

## Overview

SAFE-RO is a Python-based platform for environmental monitoring in Romania, focusing on flood detection and vegetation analysis using satellite imagery. It provides a web-based graphical user interface (GUI) for interactive analysis, a RESTful API for programmatic access, and a data pipeline for acquiring and processing satellite data.

## Project Structure

The project is organized into the following directories:

- `src/safe_ro`: Contains the main source code for the project.
  - `core`: Core scientific logic for raster data processing.
  - `clients`: Modules for interacting with external services like Google Earth Engine, Google Drive, and NASA FIRMS.
  - `interfaces`: User interfaces, including the Streamlit web application and the FastAPI.
- `scripts`: Standalone scripts for tasks like data acquisition.
- `tests`: Unit and integration tests for the project.

## Getting Started

### Prerequisites

- Python 3.9+
- Pip
- Git

### Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    ```
2.  Navigate to the project directory:
    ```bash
    cd SAFE_RO_Project
    ```
3.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

1.  **Google Earth Engine**: Create a file `.streamlit/secrets.toml` and add your GEE project ID:
    ```toml
    gee_project = "your-project-id"
    ```
2.  **Google Drive**: For local development, run the application once to authenticate with Google Drive. This will create a `mycreds.txt` file. For deployment, add your Google Drive credentials as a Streamlit secret:
    ```toml
    gdrive_creds_json = "..."
    ```
3.  **FIRMS**: Add your FIRMS API key to `.streamlit/secrets.toml`:
    ```toml
    firms_api_key = "your-api-key"
    ```

## How to Run

### Web Application

To run the Streamlit web application, use the following command:

```bash
streamlit run src/safe_ro/interfaces/main_app.py
```

### API

To run the FastAPI, use the following command:

```bash
uvicorn safe_ro.interfaces.safe_ro_api:app --reload
```

The API documentation will be available at `http://127.0.0.1:8000/docs`.

### Tests

To run the test suite, use the following command:

```bash
pytest
```