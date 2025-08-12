import serial

# Update to match the reader port
ser = serial.Serial('/dev/pts/7', baudrate=9600, timeout=1)

while True:
    data = ser.readline().decode().strip()
    if data:
        print(f"Received: {data}")
