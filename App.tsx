import { useState, useCallback, useRef } from 'react'
import { Upload, Download, ImageIcon, Sparkles, AlertCircle } from 'lucide-react'
import {
  ReactCompareSlider,
  ReactCompareSliderImage
} from 'react-compare-slider'
import './App.css'

const API_BASE_URL = ''  // Use same origin for API calls

const SUPPORTED_FORMATS = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/bmp']
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB
const MIN_DIMENSION = 50

type Resolution = '2k' | '4k'

interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string>('')
  const [upscaledUrl, setUpscaledUrl] = useState<string>('')
  const [resolution, setResolution] = useState<Resolution>('4k')
  const [isProcessing, setIsProcessing] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const addToast = useCallback((message: string, type: 'success' | 'error') => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 5000)
  }, [])

  const validateFile = useCallback((file: File): string | null => {
    if (!SUPPORTED_FORMATS.includes(file.type)) {
      return 'Unsupported format. Please upload JPG, PNG, WebP, or BMP.'
    }

    if (file.size > MAX_FILE_SIZE) {
      return `File too large. Maximum size is ${MAX_FILE_SIZE / (1024 * 1024)}MB.`
    }

    return null
  }, [])

  const validateImageDimensions = useCallback((file: File): Promise<string | null> => {
    return new Promise((resolve) => {
      const img = new Image()
      img.onload = () => {
        if (img.width < MIN_DIMENSION || img.height < MIN_DIMENSION) {
          resolve(`Image too small. Minimum dimensions: ${MIN_DIMENSION}x${MIN_DIMENSION}px`)
        } else {
          resolve(null)
        }
      }
      img.onerror = () => resolve('Invalid image file')
      img.src = URL.createObjectURL(file)
    })
  }, [])

  const handleFileSelect = useCallback(async (file: File) => {
    const validationError = validateFile(file)
    if (validationError) {
      addToast(validationError, 'error')
      return
    }

    const dimensionError = await validateImageDimensions(file)
    if (dimensionError) {
      addToast(dimensionError, 'error')
      return
    }

    setSelectedFile(file)
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    setUpscaledUrl('')
  }, [validateFile, validateImageDimensions, addToast])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const file = e.dataTransfer.files[0]
    if (file) {
      handleFileSelect(file)
    }
  }, [handleFileSelect])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFileSelect(file)
    }
  }, [handleFileSelect])

  const handleUpscale = useCallback(async () => {
    if (!selectedFile) return

    setIsProcessing(true)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('resolution', resolution)

      const response = await fetch(`${API_BASE_URL}/api/upscale`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to upscale image' }))
        throw new Error(errorData.detail || 'Failed to upscale image')
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      setUpscaledUrl(url)
      addToast('Image upscaled successfully!', 'success')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'An error occurred while processing your image'
      addToast(message, 'error')
    } finally {
      setIsProcessing(false)
    }
  }, [selectedFile, resolution, addToast])

  const handleDownload = useCallback(() => {
    if (!upscaledUrl || !selectedFile) return

    const link = document.createElement('a')
    link.href = upscaledUrl
    const fileName = selectedFile.name.replace(/\.[^/.]+$/, '')
    link.download = `${fileName}_${resolution}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    addToast('Image downloaded successfully!', 'success')
  }, [upscaledUrl, selectedFile, resolution, addToast])

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      {/* Toast Notifications */}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`px-6 py-3 rounded-lg shadow-lg flex items-center gap-3 animate-in slide-in-from-right ${
              toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
          >
            <AlertCircle className="w-5 h-5" />
            <span>{toast.message}</span>
          </div>
        ))}
      </div>

      {/* Header */}
      <header className="border-b border-gray-700 bg-gray-900/50 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <Sparkles className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
              PixelForge AI Upscaler
            </h1>
          </div>
          <p className="mt-2 text-gray-400">Transform your images with AI-powered upscaling</p>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-6xl mx-auto space-y-8">
          {/* Upload Section */}
          <div className="bg-gray-800/50 backdrop-blur-sm rounded-xl p-8 border border-gray-700">
            <h2 className="text-2xl font-semibold mb-6 flex items-center gap-2">
              <Upload className="w-6 h-6 text-primary" />
              Upload Image
            </h2>

            {/* Drag and Drop Zone */}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-all ${
                isDragging
                  ? 'border-primary bg-primary/10'
                  : 'border-gray-600 hover:border-primary/50 hover:bg-gray-700/30'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/jpg,image/png,image/webp,image/bmp"
                onChange={handleFileInputChange}
                className="hidden"
              />
              
              {selectedFile ? (
                <div className="space-y-3">
                  <ImageIcon className="w-16 h-16 mx-auto text-primary" />
                  <p className="text-lg font-medium text-gray-200">{selectedFile.name}</p>
                  <p className="text-sm text-gray-400">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                  <p className="text-xs text-gray-500">Click to change</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <Upload className="w-16 h-16 mx-auto text-gray-500" />
                  <p className="text-lg font-medium text-gray-300">
                    Drag and drop your image here
                  </p>
                  <p className="text-sm text-gray-400">or click to browse</p>
                  <p className="text-xs text-gray-500">
                    Supports: JPG, PNG, WebP, BMP (Max 20MB)
                  </p>
                </div>
              )}
            </div>

            {/* Resolution Selection */}
            {selectedFile && (
              <div className="mt-6 space-y-4">
                <h3 className="text-lg font-medium text-gray-200">Select Resolution</h3>
                <div className="flex gap-4">
                  <label className="flex-1">
                    <input
                      type="radio"
                      name="resolution"
                      value="2k"
                      checked={resolution === '2k'}
                      onChange={(e) => setResolution(e.target.value as Resolution)}
                      className="sr-only peer"
                    />
                    <div className="p-4 rounded-lg border-2 border-gray-600 cursor-pointer transition-all peer-checked:border-primary peer-checked:bg-primary/10 hover:border-primary/50">
                      <p className="font-semibold text-gray-200">2K Resolution</p>
                      <p className="text-sm text-gray-400">2560 x 1440</p>
                    </div>
                  </label>
                  <label className="flex-1">
                    <input
                      type="radio"
                      name="resolution"
                      value="4k"
                      checked={resolution === '4k'}
                      onChange={(e) => setResolution(e.target.value as Resolution)}
                      className="sr-only peer"
                    />
                    <div className="p-4 rounded-lg border-2 border-gray-600 cursor-pointer transition-all peer-checked:border-primary peer-checked:bg-primary/10 hover:border-primary/50">
                      <p className="font-semibold text-gray-200">4K Resolution</p>
                      <p className="text-sm text-gray-400">3840 x 2160</p>
                    </div>
                  </label>
                </div>

                {/* Upscale Button */}
                <button
                  onClick={handleUpscale}
                  disabled={isProcessing}
                  className="w-full py-3 px-6 bg-gradient-to-r from-primary to-secondary text-white font-semibold rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
                >
                  {isProcessing ? (
                    <>
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-5 h-5" />
                      Upscale Image
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Comparison Section */}
          {upscaledUrl && (
            <div className="bg-gray-800/50 backdrop-blur-sm rounded-xl p-8 border border-gray-700">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-semibold flex items-center gap-2">
                  <ImageIcon className="w-6 h-6 text-primary" />
                  Before & After Comparison
                </h2>
                <button
                  onClick={handleDownload}
                  className="px-6 py-2 bg-gradient-to-r from-primary to-secondary text-white font-semibold rounded-lg hover:opacity-90 transition-all flex items-center gap-2"
                >
                  <Download className="w-5 h-5" />
                  Download {resolution.toUpperCase()} Image
                </button>
              </div>

              <div className="rounded-lg overflow-hidden border border-gray-700">
                <ReactCompareSlider
                  itemOne={<ReactCompareSliderImage src={previewUrl} alt="Original" />}
                  itemTwo={<ReactCompareSliderImage src={upscaledUrl} alt="Upscaled" />}
                  style={{ height: '600px' }}
                />
              </div>

              <div className="mt-4 flex justify-between text-sm text-gray-400">
                <span>Original Image</span>
                <span>{resolution.toUpperCase()} Upscaled</span>
              </div>
            </div>
          )}

          {/* Privacy Notice */}
          <div className="bg-gray-800/30 backdrop-blur-sm rounded-lg p-6 border border-gray-700/50">
            <h3 className="text-lg font-semibold text-gray-200 mb-2">Privacy & Security</h3>
            <p className="text-sm text-gray-400 leading-relaxed break-words">
              Your images are processed solely for upscaling purposes and are not permanently stored on our servers.
              All uploaded files are automatically deleted after processing to ensure your privacy and data security.
              We implement a rate limit of 10 requests per hour to maintain service quality for all users.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-700 bg-gray-900/50 backdrop-blur-sm mt-16">
        <div className="container mx-auto px-4 py-6 text-center text-gray-400 text-sm">
          <p>PixelForge AI Upscaler - Professional Image Enhancement Tool</p>
        </div>
      </footer>
    </div>
  )
}

export default App
