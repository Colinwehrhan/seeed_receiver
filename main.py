import serial
import time
from pythonosc import udp_client
from rich.console import Console

# --- Configuration ---
SERIAL_PORT = "COM6"  # <-- Change this to your Receiver ESP32's COM port!
BAUD_RATE = 115200
TD_IP = "127.0.0.1"
TD_PORT = 8000

console = Console()
osc_client = udp_client.SimpleUDPClient(TD_IP, TD_PORT)

def main():
    console.print(f"[cyan]Connecting to Receiver ESP32 on {SERIAL_PORT}...[/cyan]")
    
    try:
        # Open the serial port
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # Brief pause to allow the Arduino to reset on connection
        
        console.print("[bold green]Connected! Forwarding ESP-NOW data to TouchDesigner.[/bold green]")
        console.print("[dim]Listening for DATA packets and Serial Debug messages... (Press Ctrl+C to stop)[/dim]\n")
        
        while True:
            if ser.in_waiting > 0:
                # Read the incoming line from the USB cable
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                # 1. Catch the live sensor stream
                if line.startswith("DATA:"):
                    raw_data = line.replace("DATA:", "")
                    parts = raw_data.split(",")
                    
                    if len(parts) == 6:
                        try:
                            # Convert string values back to floats
                            ax, ay, az, gx, gy, gz = map(float, parts)
                            
                            # Blast the floats to TouchDesigner via OSC
                            osc_client.send_message("/mpu6050/accel", [ax, ay, az])
                            osc_client.send_message("/mpu6050/gyro", [gx, gy, gz])
                            
                        except ValueError:
                            # Silently ignore any mangled string fragments if a bit flips
                            pass 
                
                # 2. Print all other Serial debug messages to the console
                # This ensures your standard Arduino debug outputs are preserved
                elif line:
                    console.print(f"[yellow]ESP32 Debug:[/yellow] [dim]{line}[/dim]")
                    
    except serial.SerialException as e:
        console.print(f"\n[bold red]Could not open {SERIAL_PORT}.[/bold red]")
        console.print("Is the board plugged in, and is the Arduino IDE Serial Monitor closed?")
        console.print(f"[red]Error details: {e}[/red]")
    except KeyboardInterrupt:
        console.print("\n[bold red]Script stopped gracefully by user.[/bold red]")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            console.print("[dim]Serial port closed.[/dim]")

if __name__ == "__main__":
    main()