from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from PIL import Image
import io
import os
from typing import Literal
import time
from pathlib import Path

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="PixelForge AI Upscaler")

# Add rate limit exceeded handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported formats
SUPPORTED_FORMATS = {"jpg", "jpeg", "png", "webp", "bmp"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MIN_DIMENSION = 50

# Resolution presets
RESOLUTION_PRESETS = {
    "2k": (2560, 1440),
    "4k": (3840, 2160)
}

# Get the directory where this script is located
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


def validate_image(file_bytes: bytes) -> Image.Image:
    """Validate image file and return PIL Image object"""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        
        # Check format
        if img.format.lower() not in SUPPORTED_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format. Supported formats: {', '.join(SUPPORTED_FORMATS).upper()}"
            )
        
        # Check dimensions
        width, height = img.size
        if width < MIN_DIMENSION or height < MIN_DIMENSION:
            raise HTTPException(
                status_code=400,
                detail=f"Image too small. Minimum dimensions: {MIN_DIMENSION}x{MIN_DIMENSION}px"
            )
        
        return img
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail="Invalid image file")


def simulate_ai_upscale(img: Image.Image, target_resolution: str) -> Image.Image:
    """
    Simulate AI upscaling by using high-quality Lanczos resampling
    In production, this would integrate with a real AI upscaling model
    """
    target_width, target_height = RESOLUTION_PRESETS[target_resolution]
    
    # Convert to RGB if necessary (for PNG with transparency, etc.)
    if img.mode in ('RGBA', 'LA', 'P'):
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Calculate aspect ratio preserving dimensions
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height
    target_aspect = target_width / target_height
    
    # Determine final dimensions maintaining aspect ratio
    if aspect_ratio > target_aspect:
        # Width is the limiting factor
        final_width = target_width
        final_height = int(target_width / aspect_ratio)
    else:
        # Height is the limiting factor
        final_height = target_height
        final_width = int(target_height * aspect_ratio)
    
    # High-quality upscaling using Lanczos resampling
    upscaled = img.resize((final_width, final_height), Image.LANCZOS)
    
    # Simulate processing time
    time.sleep(1)  # Simulate AI processing
    
    return upscaled


@app.post("/api/upscale")
@limiter.limit("10/hour")
async def upscale_image(
    request: Request,
    file: UploadFile = File(...),
    resolution: str = Form(...)
):
    """
    Upscale image to specified resolution
    
    Rate limit: 10 requests per hour per IP
    Max file size: 20MB
    Supported formats: JPG, JPEG, PNG, WebP, BMP
    Output format: PNG
    """
    try:
        # Validate resolution parameter
        if resolution not in RESOLUTION_PRESETS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resolution. Choose from: {', '.join(RESOLUTION_PRESETS.keys()).upper()}"
            )
        
        # Read file
        file_bytes = await file.read()
        
        # Check file size
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )
        
        # Validate and load image
        img = validate_image(file_bytes)
        
        # Perform AI upscaling (simulated)
        upscaled_img = simulate_ai_upscale(img, resolution)
        
        # Convert to PNG bytes
        output_buffer = io.BytesIO()
        upscaled_img.save(output_buffer, format='PNG', optimize=True)
        output_buffer.seek(0)
        
        # Generate filename
        original_name = os.path.splitext(file.filename)[0]
        output_filename = f"{original_name}_{resolution}.png"
        
        return StreamingResponse(
            output_buffer,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{output_filename}"'
            }
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your image. Please try again."
        )


# Mount static files for frontend
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
    
    @app.get("/")
    async def serve_frontend():
        """Serve the frontend application"""
        return FileResponse(str(FRONTEND_DIR / "index.html"))
    
    @app.get("/{full_path:path}")
    async def serve_frontend_routes(full_path: str):
        """Serve frontend for all other routes (SPA routing)"""
        # Check if it's an API call
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Check if file exists
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        
        # Default to index.html for SPA routing
        return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
