# camera_viewer.py
import cv2
import numpy as np
from hole_realsense_camera import RealsenseCamera
import time

def main():
    rs = None
    try:
        print("\nInitializing camera...")
        rs = RealsenseCamera()
        
        cv2.namedWindow('Color Frame')
        cv2.setMouseCallback('Color Frame', rs.mouse_callback)
        
        print("Controls:")
        print("- Click: Measure distance")
        print("- 'q': Quit")
        print("- 's': Save frame")
        print("- ',' and '.': Adjust contrast")
        print("- '<' and '>': Adjust brightness")
        
        last_time = time.time()
        fps = 0
        
        while True:
            ret, color_frame, depth_frame = rs.get_frame_stream()
            
            if not ret:
                continue
            
            # Calculate FPS
            current_time = time.time()
            fps = 1 / (current_time - last_time)
            last_time = current_time
            
            # Add FPS to display
            cv2.putText(color_frame, f"FPS: {fps:.1f}", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Show frames
            cv2.imshow("Color Frame", color_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                cv2.imwrite(f'frame_{timestamp}.jpg', color_frame)
                print(f"Frame saved: frame_{timestamp}.jpg")
            elif key == ord(','):
                rs.params['contrast'] = max(1.0, rs.params['contrast'] - 0.1)
                print(f"\nContrast: {rs.params['contrast']:.1f}")
            elif key == ord('.'):
                rs.params['contrast'] += 0.1
                print(f"\nContrast: {rs.params['contrast']:.1f}")
            elif key == ord('<'):
                rs.params['brightness'] = max(0, rs.params['brightness'] - 5)
                print(f"\nBrightness: {rs.params['brightness']}")
            elif key == ord('>'):
                rs.params['brightness'] = min(100, rs.params['brightness'] + 5)
                print(f"\nBrightness: {rs.params['brightness']}")
    
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        if rs:
            rs.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()