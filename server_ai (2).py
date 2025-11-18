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
import torch
from super_image import EdsrModel, ImageLoader
import numpy as np

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="PixelForge AI Upscaler - Real AI Edition")

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

# AI Model Configuration
USE_AI_UPSCALING = True  # Toggle between AI and fallback methods
AI_MODEL = None  # Will be loaded on first use


def get_ai_model():
    """Load AI model (lazy loading to avoid startup delay)"""
    global AI_MODEL
    if AI_MODEL is None and USE_AI_UPSCALING:
        try:
            print("Loading EDSR AI model for super-resolution...")
            # Load EDSR model with 4x scale (pre-trained on DIV2K dataset)
            AI_MODEL = EdsrModel.from_pretrained('eugenesiow/edsr-base', scale=4)
            # Use CPU for inference (change to cuda if GPU available)
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            AI_MODEL = AI_MODEL.to(device)
            AI_MODEL.eval()
            print(f"AI model loaded successfully on {device}")
        except Exception as e:
            print(f"Failed to load AI model: {e}")
            print("Falling back to high-quality interpolation")
    return AI_MODEL


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


def ai_upscale_image(img: Image.Image, scale_factor: int = 4) -> Image.Image:
    """
    AI-powered image upscaling using EDSR (Enhanced Deep Super-Resolution)
    This uses a real deep learning model trained on high-quality image datasets
    """
    try:
        model = get_ai_model()
        if model is None:
            raise Exception("AI model not available")
        
        # Convert PIL Image to tensor
        # EDSR expects RGB images
        if img.mode != 'RGB':
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            else:
                img = img.convert('RGB')
        
        # Use ImageLoader to prepare image for the model
        inputs = ImageLoader.load_image(img)
        
        # Get device
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        inputs = inputs.to(device)
        
        # Run AI upscaling
        with torch.no_grad():
            outputs = model(inputs)
        
        # Convert tensor back to PIL Image
        output_img = outputs.squeeze().cpu().clamp(0, 255).numpy()
        output_img = output_img.transpose(1, 2, 0).astype(np.uint8)
        upscaled_img = Image.fromarray(output_img)
        
        return upscaled_img
        
    except Exception as e:
        print(f"AI upscaling failed: {e}")
        # Fallback to high-quality interpolation
        return img.resize(
            (img.width * scale_factor, img.height * scale_factor),
            Image.LANCZOS
        )


def smart_resize_to_resolution(img: Image.Image, target_resolution: str) -> Image.Image:
    """
    Intelligently upscale image to target resolution using AI
    Preserves aspect ratio and uses multiple passes if needed
    """
    target_width, target_height = RESOLUTION_PRESETS[target_resolution]
    original_width, original_height = img.size
    
    # Calculate aspect ratios
    aspect_ratio = original_width / original_height
    target_aspect = target_width / target_height
    
    # Determine target dimensions maintaining aspect ratio
    if aspect_ratio > target_aspect:
        final_width = target_width
        final_height = int(target_width / aspect_ratio)
    else:
        final_height = target_height
        final_width = int(target_height * aspect_ratio)
    
    # Calculate scale factor needed
    scale_factor_width = final_width / original_width
    scale_factor_height = final_height / original_height
    scale_factor = max(scale_factor_width, scale_factor_height)
    
    # Use AI upscaling if available and scale factor is reasonable
    if USE_AI_UPSCALING and 1.5 <= scale_factor <= 4:
        # AI models work best with fixed scale factors (2x, 3x, 4x)
        # Use 4x scale and then resize to exact dimensions
        print(f"Using AI upscaling (4x) for {original_width}x{original_height} -> {final_width}x{final_height}")
        ai_upscaled = ai_upscale_image(img, scale_factor=4)
        # Resize to exact target dimensions
        return ai_upscaled.resize((final_width, final_height), Image.LANCZOS)
    else:
        # For very small or very large scale factors, use high-quality interpolation
        print(f"Using Lanczos interpolation for scale factor {scale_factor:.2f}")
        return img.resize((final_width, final_height), Image.LANCZOS)


@app.post("/api/upscale")
@limiter.limit("10/hour")
async def upscale_image(
    request: Request,
    file: UploadFile = File(...),
    resolution: str = Form(...)
):
    """
    AI-powered image upscaling to specified resolution
    
    Uses EDSR (Enhanced Deep Super-Resolution) neural network for true AI upscaling
    Falls back to high-quality Lanczos resampling if AI processing fails
    
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
        
        # Perform AI upscaling
        print(f"Processing image: {img.size[0]}x{img.size[1]} -> {resolution.upper()}")
        upscaled_img = smart_resize_to_resolution(img, resolution)
        print(f"Upscaled to: {upscaled_img.size[0]}x{upscaled_img.size[1]}")
        
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
                "Content-Disposition": f'attachment; filename="{output_filename}"',
                "X-AI-Upscaling": "EDSR" if USE_AI_UPSCALING else "Lanczos"
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


@app.get("/api/info")
async def get_info():
    """Get information about the AI upscaling service"""
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    return {
        "service": "PixelForge AI Upscaler",
        "version": "2.0.0",
        "ai_enabled": USE_AI_UPSCALING,
        "ai_model": "EDSR (Enhanced Deep Super-Resolution)" if USE_AI_UPSCALING else None,
        "device": device,
        "supported_resolutions": list(RESOLUTION_PRESETS.keys()),
        "supported_formats": list(SUPPORTED_FORMATS),
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "rate_limit": "10 requests per hour per IP"
    }


# Mount static files for frontend (only if directory exists)
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "assets").exists():
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
else:
    @app.get("/")
    async def root():
        """API-only mode - frontend not available"""
        return {
            "message": "PixelForge AI Upscaler API",
            "version": "2.0.0",
            "ai_enabled": USE_AI_UPSCALING,
            "endpoints": {
                "upscale": "POST /api/upscale",
                "info": "GET /api/info"
            }
        }


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("PixelForge AI Upscaler - Real AI Edition")
    print("=" * 60)
    print(f"AI Upscaling: {'ENABLED' if USE_AI_UPSCALING else 'DISABLED'}")
    print(f"Device: {'GPU (CUDA)' if torch.cuda.is_available() else 'CPU'}")
    print("AI Model: EDSR (Enhanced Deep Super-Resolution)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
