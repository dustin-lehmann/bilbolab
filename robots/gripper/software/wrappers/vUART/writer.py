import serial
import time

# Update to match the writer port
ser = serial.Serial('/dev/pts/6', baudrate=9600, timeout=1)

while True:
    message = "Hello from Program 1!"
    ser.write(message.encode())
    print(f"Sent: {message}")
    time.sleep(2)  # Send a message every 2 seconds
