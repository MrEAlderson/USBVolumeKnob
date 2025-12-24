import asyncio
import board
import countio
import digitalio
import time
import keypad
import analogio
import microcontroller
import usb_hid
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

PIN_SW = analogio.AnalogIn(board.GP26)
#PIN_SW = digitalio.DigitalInOut(board.GP26)
PIN_DT = digitalio.DigitalInOut(board.GP28)
PIN_CLK = digitalio.DigitalInOut(board.GP27)

# debounce fix
BUTTON_MIN_HOLD = 0.08
BUTTON_MAX_VAL_CLK_TRUE = 10_000
BUTTON_MAX_VAL_CLK_FALSE = 1_000

SLEEP = 0.001

#PIN_SW.direction = digitalio.Direction.INPUT
PIN_DT.direction = digitalio.Direction.INPUT
PIN_CLK.direction = digitalio.Direction.INPUT
USB_CONTROL = ConsumerControl(usb_hid.devices)

button_clk_value = PIN_CLK.value
button_toggle_time = 0
button_toggled = False
button_mode_count = 0

async def on_rotate(val):
    global button_toggle_time
    global button_toggled
    
    # False: Clockwise
    direction = PIN_DT.value == val
    
    if not button_toggled: # debounce fix
        button_toggle_time = 0
    
    print(f"Rotate: {direction}")
    
    if direction:
        USB_CONTROL.send(ConsumerControlCode.VOLUME_DECREMENT)
    else:
        USB_CONTROL.send(ConsumerControlCode.VOLUME_INCREMENT)
    
async def on_button_press():
    print("Button: Press")
    USB_CONTROL.send(ConsumerControlCode.PLAY_PAUSE)

async def on_button_release():
    global button_toggle_time
    global button_mode_count
    
    hold_time = time.monotonic() - button_toggle_time - BUTTON_MIN_HOLD
    
    print(f"Button: Release ({hold_time} s)")
    
    # bootloader mode
    if hold_time > 5:
        button_mode_count = button_mode_count + 1
        
        if button_mode_count == 2:
            print(f"Entering bootloader...")
            await asyncio.sleep(1)
            microcontroller.on_next_reset(microcontroller.RunMode.UF2)
            microcontroller.reset()
    else:
        button_mode_count = 0

async def main():
    rotate_task = asyncio.create_task(catch_interrupt(PIN_CLK, on_rotate))
    button_task = asyncio.create_task(catch_button_toggle())
    await asyncio.gather(rotate_task, button_task)

async def catch_interrupt(pin, onChange):
    global button_clk_value
    
    while True:
        new_state = PIN_CLK.value
        
        if new_state != button_clk_value:
            button_clk_value = new_state
            await onChange(new_state)
        
        await asyncio.sleep(SLEEP)
    
async def catch_button_toggle():
    global button_toggle_time
    global button_toggled
    global button_clk_value
    
    last_state = False
    
    while True:
        # prints different values when (not) clicked depending on rotating state
        max_val = BUTTON_MAX_VAL_CLK_TRUE if button_clk_value else BUTTON_MAX_VAL_CLK_FALSE
        new_state = PIN_SW.value < max_val

        # debug
        print(f"{PIN_SW.value} {button_clk_value} {new_state} {max_val}")
        
        # State changed
        if new_state != last_state:
            last_state = new_state
            
            # Use time to make sure it was pressed (fix inconsistent states)
            if not new_state:
                button_toggle_time = time.monotonic()
            else:
                # Released button
                if button_toggled:
                    button_toggled = False
                    await on_button_release()
                
                button_toggle_time = 0
        
        # Make sure button is humanly pressed for min x ms
        else:
            if button_toggle_time != 0 and not button_toggled and (time.monotonic() - button_toggle_time) > BUTTON_MIN_HOLD:
                button_toggled = True
                await on_button_press()
        
        await asyncio.sleep(SLEEP)

asyncio.run(main())