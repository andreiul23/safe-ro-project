a# SAFE-RO Project

## Overview

SAFE-RO is a Python-based platform for environmental monitoring in Romania, leveraging satellite imagery for flood detection, vegetation analysis, and fire monitoring. It offers a suite of tools, including a web-based graphical user interface (GUI) for interactive analysis, a RESTful API for programmatic access, and a data pipeline for acquiring and processing satellite data from various sources.

The platform is designed for a range of users, from citizens checking local conditions to authorities performing detailed analysis.

## Features

-   **Multi-Hazard Monitoring**: Analyze and visualize data for floods, vegetation health (NDVI), and active fires.
-   **Multiple Data Sources**: 
    -   **Google Earth Engine**: Real-time analysis of Sentinel-1 (Radar) and Sentinel-2 (Optical) data.
    -   **Google Drive**: Process your own satellite imagery stored in Google Drive.
    -   **Local Upload**: Analyze raster files directly from your computer.
    -   **NASA FIRMS**: Fetch and display active fire data.
-   **Interactive Web Application**: 
    -   A user-friendly interface built with Streamlit.
    -   Different modes for various user needs: a citizen-facing app, an authority dashboard, and a local analysis workbench.
    -   Interactive maps with Folium for visualizing data overlays.
-   **RESTful API**: 
    -   A FastAPI-based API for programmatic access to core functionalities.
    -   Endpoints for NDVI calculation and flood detection.
-   **Modular and Extensible**: The project is organized into distinct modules for core logic, clients, and interfaces, making it easy to extend and adapt.

## Project Structure

The project is organized into the following directories:

-   `src/safe_ro`: Contains the main source code for the project.
    -   `core`: Core scientific logic for raster data processing (NDVI, flood detection).
    -   `clients`: Modules for interacting with external services like Google Earth Engine, Google Drive, and NASA FIRMS.
    -   `interfaces`: User interfaces, including the Streamlit web application (`main_app.py`) and the FastAPI (`safe_ro_api.py`).
-   `scripts`: Standalone scripts for tasks like data acquisition.
-   `tests`: Unit and integration tests for the project.

## Getting Started

### Prerequisites

-   Python 3.9+
-   Pip
-   Git

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
2.  **Google Drive**: For local development, you need to authenticate with Google Drive. Run the following command and follow the instructions in your browser:
    ```bash
    python scripts/authenticate_gdrive.py
    ```
    This will create a `mycreds.txt` file. For deployment, add your Google Drive credentials as a Streamlit secret:
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
uvicorn src.safe_ro.interfaces.safe_ro_api:app --reload
```

The API documentation will be available at `http://127.0.0.1:8000/docs`.

### Tests

To run the test suite, use the following command:

```bash
pytest
```