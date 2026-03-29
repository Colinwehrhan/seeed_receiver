import asyncio
import struct
from bleak import BleakScanner, BleakClient
from rich.console import Console
from rich import inspect
from pythonosc import udp_client

# --- Configuration ---
DEVICE_NAME_FILTER = "colinXIAO"
TARGET_CHAR_UUID = "c46d641f-0926-40a6-bdcf-60230fc1f205"
TD_IP = "127.0.0.1"
TD_PORT = 8000

# --- Initialize Tools ---
console = Console()
osc_client = udp_client.SimpleUDPClient(TD_IP, TD_PORT)

# Thread-safe async events and queues
exit_event = asyncio.Event()
data_queue = asyncio.Queue()

async def process_data():
    """
    Background task to unpack data and send to TouchDesigner.
    This acts as a 'pacemaker' to un-clump delayed Bluetooth packets.
    """
    while not exit_event.is_set():
        try:
            # Wait for data to appear in the queue
            data = await asyncio.wait_for(data_queue.get(), timeout=0.5)
            
            # 1. Unpack the 24 raw bytes into 6 floats (Little-endian)
            ax, ay, az, gx, gy, gz = struct.unpack('<ffffff', data)

            # 2. Send to TouchDesigner via OSC
            osc_client.send_message("/mpu6050/accel", [ax, ay, az])
            osc_client.send_message("/mpu6050/gyro", [gx, gy, gz])

            # 3. THE PACEMAKER
            # Forces Python to wait ~15ms before processing the next packet in the queue.
            # This turns bursty/laggy radio data back into a smooth 60 FPS stream.
            await asyncio.sleep(0.015)

        except asyncio.TimeoutError:
            # Normal timeout if the ESP32 hasn't sent anything, keep waiting
            continue
        except Exception as e:
            console.print(f"[red]Error processing data: {e}[/red]")

async def main():
    console.print(f"Scanning for device containing: '{DEVICE_NAME_FILTER}'...")
    
    device = await BleakScanner.find_device_by_filter(
        lambda bd, ad: bd.name and DEVICE_NAME_FILTER in bd.name, timeout=15
    )
    
    if device is None:
        console.print("[bold red]Device not found. Make sure the ESP32 is on and advertising.[/bold red]")
        return

    # Print device details to confirm we found the right one
    console.print("\n[bold green]Device Found![/bold green]")
    inspect(device)
    
    async with BleakClient(device) as client:
        # THE CALLBACK: This is lightning fast. 
        # It only drops the raw bytes into the queue and immediately finishes.
        def callback_data(sender, data):
            data_queue.put_nowait(data)

        characteristic = client.services.get_characteristic(TARGET_CHAR_UUID)

        if characteristic:
            await client.start_notify(characteristic, callback_data)
            console.print(f"[bold cyan]Connected! Listening for MPU6050 data and sending to TD...[/bold cyan]")
            console.print("[dim](Press Ctrl+C to stop)[/dim]")
            
            # Start the background consumer task
            processor_task = asyncio.create_task(process_data())
            
            try:
                # Keep the main loop alive until we receive an exit signal
                await exit_event.wait()
            finally:
                # Clean up when closing
                await client.stop_notify(characteristic)
                processor_task.cancel()
        else:
            console.print(f"[bold red]UUID {TARGET_CHAR_UUID} not found on this device![/bold red]")

if __name__ == "__main__":
    try:
        # Run the main loop
        asyncio.run(main())
    except KeyboardInterrupt:
        # This gracefully catches when you physically press Ctrl+C
        exit_event.set()
        console.print("\n[bold red]Program exited gracefully by user.[/bold red]")