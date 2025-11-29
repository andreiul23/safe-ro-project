import ee

class GEEClient:
    def __init__(self, project=None):
        # Initialize Google Earth Engine (if not already initialized)
        try:
            ee.Initialize(project=project)
        except Exception:
            # If already initialized or other error, proceed
            pass

    def get_ndvi(self, aoi, start_date, end_date):
        # Placeholder for actual GEE NDVI retrieval logic
        print(f"GEEClient: get_ndvi called for AOI: {aoi}, dates: {start_date} to {end_date}")
        return None # Return dummy data or None

    def get_flood_data(self, aoi, start_date, end_date):
        # Placeholder for actual GEE flood data retrieval logic
        print(f"GEEClient: get_flood_data called for AOI: {aoi}, dates: {start_date} to {end_date}")
        return None # Return dummy data or None
