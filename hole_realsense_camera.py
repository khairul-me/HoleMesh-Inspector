# realsense_camera.py
import pyrealsense2 as rs
import numpy as np
import cv2
import threading
import queue
import time

class RealsenseCamera:
    def __init__(self):
        # Initialize basic components
        self.pipeline = None
        self.align = None
        self.depth_scale = None
        self.clicked_point = None
        
        # Threading components
        self.frame_queue = queue.Queue(maxsize=2)
        self.running = False
        self.frame_thread = None
        
        # Display flags
        self.draw_distance = True
        self.show_binary = False
        self.processing = True
        
        # Detection parameters (optimized for mesh)
        self.params = {
            'min_area': 20,          # Minimum hole area
            'max_area': 200,         # Maximum hole area
            'threshold': 70,         # Base threshold
            'blur_size': 3,          # Blur kernel size
            'contrast': 1.4,         # Contrast enhancement
            'brightness': 30,        # Brightness adjustment
            'grid_size': 15,         # Expected mesh grid size
            'dilate_size': 2,        # Morphological operation size
            'min_aspect_ratio': 0.5, # Minimum width/height ratio
            'max_aspect_ratio': 2.0  # Maximum width/height ratio
        }
        
        # Initialize camera
        self.init_camera()
        self.start_frame_thread()

    def init_camera(self):
        try:
            # Reset any existing pipeline
            if self.pipeline:
                self.pipeline.stop()
            
            # Create pipeline
            self.pipeline = rs.pipeline()
            config = rs.config()
            
            # Check for camera
            ctx = rs.context()
            devices = ctx.query_devices()
            if not devices:
                raise RuntimeError("No RealSense device found")
                
            device = devices[0]
            print(f"Found device: {device.get_info(rs.camera_info.name)}")
            
            # Configure streams
            config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 15)
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 15)
            
            # Start streaming
            profile = self.pipeline.start(config)
            
            # Configure depth sensor
            depth_sensor = profile.get_device().first_depth_sensor()
            self.depth_scale = depth_sensor.get_depth_scale()
            
            # Optimize sensor settings
            if depth_sensor.supports(rs.option.enable_auto_exposure):
                depth_sensor.set_option(rs.option.enable_auto_exposure, 0)
            if depth_sensor.supports(rs.option.laser_power):
                depth_sensor.set_option(rs.option.laser_power, 360)
            
            # Create align object
            self.align = rs.align(rs.stream.color)
            
            print("Camera initialized successfully")
            time.sleep(1)
            
        except Exception as e:
            print(f"Error initializing camera: {str(e)}")
            if self.pipeline:
                self.pipeline.stop()
            raise

    def detect_holes(self, image):
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Enhance contrast and brightness
            gray = cv2.convertScaleAbs(gray, 
                alpha=self.params['contrast'], 
                beta=self.params['brightness'])
            
            # Apply blur
            blurred = cv2.GaussianBlur(gray, 
                (self.params['blur_size'], self.params['blur_size']), 0)
            
            # Adaptive thresholding
            thresh = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                21,
                5
            )
            
            # Morphological operations
            kernel = np.ones((self.params['dilate_size'], 
                self.params['dilate_size']), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=1)
            thresh = cv2.erode(thresh, kernel, iterations=1)
            
            # Find contours with hierarchy
            contours, hierarchy = cv2.findContours(
                thresh,
                cv2.RETR_CCOMP,
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            valid_holes = []
            if hierarchy is not None:
                hierarchy = hierarchy[0]
                for i, cnt in enumerate(contours):
                    area = cv2.contourArea(cnt)
                    
                    if (hierarchy[i][3] != -1 and 
                        self.params['min_area'] <= area <= self.params['max_area']):
                        
                        x, y, w, h = cv2.boundingRect(cnt)
                        aspect_ratio = float(w)/h
                        
                        if (self.params['min_aspect_ratio'] <= aspect_ratio <= 
                            self.params['max_aspect_ratio']):
                            
                            M = cv2.moments(cnt)
                            if M["m00"] != 0:
                                cx = int(M["m10"] / M["m00"])
                                cy = int(M["m01"] / M["m00"])
                                valid_holes.append({
                                    'contour': cnt,
                                    'center': (cx, cy),
                                    'area': area,
                                    'width': w,
                                    'height': h
                                })
            
            return valid_holes, thresh
            
        except Exception as e:
            print(f"Error in hole detection: {str(e)}")
            return [], None

    def draw_analysis(self, color_image, holes, depth_frame, binary_image=None):
        output = color_image.copy()
        
        # Draw holes
        for hole in holes:
            # Contour
            cv2.drawContours(output, [hole['contour']], -1, (0, 255, 0), 1)
            
            # Center point
            center = hole['center']
            cv2.circle(output, center, 2, (0, 0, 255), -1)
            
            # Distance measurement
            if self.draw_distance:
                distance = depth_frame[center[1], center[0]] * self.depth_scale
                cv2.putText(output, f"{distance:.2f}m", 
                           (center[0]-20, center[1]-5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)
        
        # Draw statistics
        stats = [
            f"FPS: {self.current_fps:.1f}" if hasattr(self, 'current_fps') else "",
            f"Holes detected: {len(holes)}",
            f"Threshold: {self.params['threshold']}",
            f"Min area: {self.params['min_area']}"
        ]
        
        for i, text in enumerate(stats):
            cv2.putText(output, text, (10, 30 + i*25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Draw clicked point measurement
        if self.clicked_point:
            x, y = self.clicked_point
            distance = depth_frame[y, x] * self.depth_scale
            cv2.circle(output, (x, y), 4, (0, 0, 255), -1)
            cv2.putText(output, f"Point dist: {distance:.3f}m", 
                      (x + 10, y), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        return output

    def frame_capture_thread(self):
        while self.running:
            try:
                frames = self.pipeline.wait_for_frames(timeout_ms=1000)
                aligned_frames = self.align.process(frames)
                
                depth_frame = aligned_frames.get_depth_frame()
                color_frame = aligned_frames.get_color_frame()
                
                if not depth_frame or not color_frame:
                    continue
                
                depth_image = np.asanyarray(depth_frame.get_data())
                color_image = np.asanyarray(color_frame.get_data())
                
                try:
                    self.frame_queue.put_nowait((color_image, depth_image))
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait((color_image, depth_image))
                    except:
                        pass
                        
            except Exception as e:
                print(f"Error in frame capture: {str(e)}")
                time.sleep(0.1)

    def start_frame_thread(self):
        self.running = True
        self.frame_thread = threading.Thread(target=self.frame_capture_thread)
        self.frame_thread.daemon = True
        self.frame_thread.start()

    def get_frame_stream(self):
        try:
            color_image, depth_image = self.frame_queue.get(timeout=0.5)
            
            if self.processing:
                holes, binary = self.detect_holes(color_image)
                annotated_image = self.draw_analysis(color_image, holes, depth_image, binary)
                
                if self.show_binary and binary is not None:
                    # Show binary image alongside main image
                    binary_colored = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
                    annotated_image = np.hstack((annotated_image, binary_colored))
                
                return True, annotated_image, depth_image
            else:
                return True, color_image, depth_image
                
        except:
            return False, None, None

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.clicked_point = (x, y)

    def release(self):
        self.running = False
        if self.frame_thread:
            self.frame_thread.join(timeout=1.0)
        if self.pipeline:
            self.pipeline.stop()