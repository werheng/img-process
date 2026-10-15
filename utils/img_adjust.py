#!/usr/bin/env python3
"""
Image pre-processing utilities for the picture filter Flask service.

Provides color-preserving enhancement operations based on OpenCV:
- Brightness and contrast adjustment
- Overexposure reduction
- Histogram equalization / CLAHE
- Gamma correction
- Denoising
"""

import os
from pathlib import Path
from typing import List

import cv2
import numpy as np


class ImagePreProcessor:
    """Image pre-processing tool for enhancing maps and reducing overexposure"""
    
    def __init__(self, image_path: str):
        """
        Initialize pre-processor with image
        
        Args:
            image_path: Path to input image
        """
        self.image_path = image_path
        # Load image with color preservation
        self.original = cv2.imread(image_path, cv2.IMREAD_COLOR)
        
        if self.original is None:
            raise ValueError(f"Failed to load image: {image_path}")
        
        self.processed = self.original.copy()
        self.is_color = len(self.original.shape) == 3
    
    def adjust_brightness_contrast(self, brightness: float = 0,
                                   contrast: float = 1.0) -> np.ndarray:
        """
        Adjust image brightness and contrast (color-preserving)
        
        Args:
            brightness: Brightness adjustment (-128 to 127)
            contrast: Contrast multiplier (0.5 to 2.0)
            
        Returns:
            Processed image (preserves color if input is color)
        """
        result = self.original.copy()
        
        if self.is_color:
            # Convert to LAB color space
            lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
            
            # Adjust only L channel
            l_channel = cv2.convertScaleAbs(l_channel, alpha=contrast, beta=brightness)
            
            # Convert back to BGR
            lab[:, :, 0] = l_channel
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            result = cv2.convertScaleAbs(result, alpha=contrast, beta=brightness)
        
        self.processed = result
        return result
    
    def reduce_overexposure(self, threshold: int = 200,
                           reduction_factor: float = 0.5) -> np.ndarray:
        """
        Reduce overexposure in image by dimming bright areas (color-preserving)
        
        Args:
            threshold: Pixel value threshold for overexposure (0-255)
            reduction_factor: How much to reduce bright pixels (0.0-1.0)
            
        Returns:
            Processed image with reduced overexposure (preserves color)
        """
        result = self.original.copy()
        
        if self.is_color:
            # Convert to LAB color space
            lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0].astype(np.float32)
            
            # Create mask for overexposed areas in L channel
            mask = l_channel > threshold
            
            # Reduce brightness in overexposed areas
            l_channel[mask] = l_channel[mask] * (1.0 - reduction_factor * (l_channel[mask] - threshold) / (255 - threshold))
            
            # Clip and convert back
            l_channel = np.clip(l_channel, 0, 255).astype(np.uint8)
            lab[:, :, 0] = l_channel
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # Grayscale processing
            l_channel = result.astype(np.float32)
            mask = l_channel > threshold
            l_channel[mask] = l_channel[mask] * (1.0 - reduction_factor * (l_channel[mask] - threshold) / (255 - threshold))
            result = np.clip(l_channel, 0, 255).astype(np.uint8)
        
        self.processed = result
        return self.processed
    
    def histogram_equalization(self, adaptive: bool = True) -> np.ndarray:
        """
        Apply histogram equalization to improve contrast (color-preserving)
        
        Args:
            adaptive: Use CLAHE (adaptive) instead of global equalization
            
        Returns:
            Processed image with enhanced contrast (preserves color)
        """
        result = self.original.copy()
        
        if self.is_color:
            # Convert to LAB color space
            lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
            
            # Apply CLAHE only to L channel
            if adaptive:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l_channel = clahe.apply(l_channel)
            else:
                l_channel = cv2.equalizeHist(l_channel)
            
            # Convert back to BGR
            lab[:, :, 0] = l_channel
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # Grayscale processing
            if adaptive:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                result = clahe.apply(result)
            else:
                result = cv2.equalizeHist(result)
        
        self.processed = result
        return self.processed
    
    def gamma_correction(self, gamma: float = 1.0) -> np.ndarray:
        """
        Apply gamma correction to adjust image brightness (color-preserving)
        
        Args:
            gamma: Gamma value (<1.0 brightens, >1.0 darkens)
            
        Returns:
            Gamma-corrected image (preserves color)
        """
        result = self.original.copy()
        
        if self.is_color:
            # Convert to LAB color space
            lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
            
            # Create lookup table
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255
                             for i in range(256)]).astype(np.uint8)
            
            # Apply gamma correction only to L channel
            l_channel = cv2.LUT(l_channel, table)
            
            # Convert back to BGR
            lab[:, :, 0] = l_channel
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # Grayscale processing
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255
                             for i in range(256)]).astype(np.uint8)
            result = cv2.LUT(result, table)
        
        self.processed = result
        return self.processed
    
    def adaptive_threshold(self, block_size: int = 11,
                          c: float = 2) -> np.ndarray:
        """
        Apply adaptive thresholding for better edge detection
        
        Note: This operation converts image to binary (black/white),
        so color information is inherently lost.
        
        Args:
            block_size: Size of neighborhood for adaptive threshold
            c: Constant subtracted from mean
            
        Returns:
            Thresholded image (binary, grayscale)
        """
        # Adaptive threshold only works on grayscale
        if self.is_color:
            # Convert to grayscale for thresholding
            gray = cv2.cvtColor(self.original, cv2.COLOR_BGR2GRAY)
            result = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, block_size, c
            )
        else:
            result = cv2.adaptiveThreshold(
                self.original, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, block_size, c
            )
        
        self.processed = result
        return self.processed
    
    def denoise(self, strength: int = 10) -> np.ndarray:
        """
        Denoise image using non-local means (color-preserving)
        
        Args:
            strength: Denoising strength (higher = more aggressive)
            
        Returns:
            Denoised image (preserves color if input is color)
        """
        if self.is_color:
            # Use color-aware denoising for color images
            result = cv2.fastNlMeansDenoisingColored(
                self.original, None, strength, strength, 7, 21
            )
        else:
            # Use standard denoising for grayscale
            result = cv2.fastNlMeansDenoising(self.original, None, strength, 10, 7)
        
        self.processed = result
        return self.processed
    
    def combine_preprocessing(self,
                             brightness: float = 0,
                             contrast: float = 1.0,
                             reduce_overexpose: bool = True,
                             overexpose_threshold: int = 220,
                             use_clahe: bool = True,
                             gamma: float = 1.0) -> np.ndarray:
        """
        Apply combined preprocessing steps (color-preserving)
        
        Args:
            brightness: Brightness adjustment
            contrast: Contrast multiplier
            reduce_overexpose: Whether to reduce overexposure
            overexpose_threshold: Threshold for overexposure detection
            use_clahe: Whether to use CLAHE
            gamma: Gamma correction value
            
        Returns:
            Fully processed image (preserves color if input is color)
        """
        result = self.original.copy()
        
        # Convert to LAB color space for color-preserving processing
        if self.is_color:
            lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
        else:
            l_channel = result
        
        # Step 1: Brightness and contrast (only on L channel)
        if brightness != 0 or contrast != 1.0:
            l_channel = cv2.convertScaleAbs(l_channel, alpha=contrast, beta=brightness)
        
        # Step 2: Reduce overexposure (only on L channel)
        if reduce_overexpose:
            mask = l_channel > overexpose_threshold
            l_channel_float = l_channel.astype(np.float32)
            l_channel_float[mask] = l_channel_float[mask] * 0.7  # Reduce to 70%
            l_channel = np.clip(l_channel_float, 0, 255).astype(np.uint8)
        
        # Step 3: Gamma correction (only on L channel)
        if gamma != 1.0:
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255
                             for i in range(256)]).astype(np.uint8)
            l_channel = cv2.LUT(l_channel, table)
        
        # Step 4: CLAHE (only on L channel)
        if use_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
        
        # Convert back to BGR if original was color
        if self.is_color:
            lab[:, :, 0] = l_channel
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            result = l_channel
        
        self.processed = result
        return result
    
    def save(self, output_path: str):
        """
        Save processed image
        
        Args:
            output_path: Path to save the image
        """
        cv2.imwrite(output_path, self.processed)
        print(f"Processed image saved to: {output_path}")
    
    def show_comparison(self, window_name: str = "Image Comparison"):
        """
        Display original and processed images side by side
        
        Args:
            window_name: Window title
        """
        # Create comparison image
        comparison = np.hstack([self.original, self.processed])
        
        cv2.imshow(window_name, comparison)
        print(f"Press any key to close comparison window...")
        cv2.waitKey(0)
        cv2.destroyWindow(window_name)


# 支持的图片扩展名
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")


def is_supported_image(filename: str) -> bool:
    """判断文件名扩展名是否为支持的图片类型。"""
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def find_images(input_dir: str) -> List[str]:
    """递归查找目录下所有支持的图片文件（按名称排序，保证确定性）。"""
    root = Path(input_dir)
    files = [
        str(p)
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(files)


def process_image_file(input_path: str, output_path: str, **kwargs) -> bool:
    """对单个本地图片文件执行增强处理并写出结果。

    Args:
        input_path: 输入图片本地路径
        output_path: 输出图片本地路径
        **kwargs: 处理参数（brightness/contrast/reduce_overexpose/threshold/use_clahe/gamma/denoise）

    Returns:
        是否处理成功
    """
    processor = ImagePreProcessor(input_path)
    result = processor.combine_preprocessing(
        brightness=kwargs.get("brightness", 0),
        contrast=kwargs.get("contrast", 1.0),
        reduce_overexpose=kwargs.get("reduce_overexpose", False),
        overexpose_threshold=kwargs.get("threshold", 220),
        use_clahe=kwargs.get("use_clahe", False),
        gamma=kwargs.get("gamma", 1.0),
    )

    denoise = kwargs.get("denoise")
    if denoise:
        if processor.is_color:
            result = cv2.fastNlMeansDenoisingColored(result, None, denoise, denoise, 7, 21)
        else:
            result = cv2.fastNlMeansDenoising(result, None, denoise, 10, 7)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    return bool(cv2.imwrite(output_path, result))