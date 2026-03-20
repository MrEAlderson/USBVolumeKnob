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

class Knob:
    button_toggle_time = 0
    button_toggled = False
    button_mode_count = 0
    
    def __init__(self, name, pin_sw, pin_dt, pin_clk):
        pin_dt.direction = digitalio.Direction.INPUT
        pin_clk.direction = digitalio.Direction.INPUT
        
        self.name = name
        self.pin_sw = pin_sw
        self.pin_dt = pin_dt
        self.pin_clk = pin_clk
        self.button_clk_value = pin_clk.value

# Configure existing volume knobs
knobs = [
    Knob(
        "Left",
        analogio.AnalogIn(board.GP26), # sw
        digitalio.DigitalInOut(board.GP28) , # dt
        digitalio.DigitalInOut(board.GP27) # clk
    )
]

# debounce fix
BUTTON_MIN_HOLD = 0.08
BUTTON_MAX_VAL_CLK_TRUE = 10_000
BUTTON_MAX_VAL_CLK_FALSE = 1_000
SLEEP = 0.001

USB_CONTROL = ConsumerControl(usb_hid.devices)

async def on_rotate(knob, val):
    # False: Clockwise
    direction = knob.pin_dt.value == val
    
    if not knob.button_toggled: # debounce fix
        knob.button_toggle_time = 0
    
    print(f"{knob.name} - Rotate: {direction}")
    
    if direction:
        USB_CONTROL.send(ConsumerControlCode.VOLUME_DECREMENT)
    else:
        USB_CONTROL.send(ConsumerControlCode.VOLUME_INCREMENT)
    
async def on_button_press(knob):
    print("Button: Press")
    USB_CONTROL.send(ConsumerControlCode.PLAY_PAUSE)

async def on_button_release(knob):
    hold_time = time.monotonic() - knob.button_toggle_time - BUTTON_MIN_HOLD
    
    print(f"{knob.name} - Button: Release ({hold_time} s)")
    
    # bootloader mode
    if hold_time > 5:
        knob.button_mode_count = knob.button_mode_count + 1
        
        if knob.button_mode_count == 2:
            print(f"{knob.name} - Entering bootloader...")
            await asyncio.sleep(1)
            microcontroller.on_next_reset(microcontroller.RunMode.UF2)
            microcontroller.reset()
    else:
        knob.button_mode_count = 0

async def main():
    tasks = [ ]
    
    for knob in knobs:
        tasks.append(asyncio.create_task(catch_interrupt(knob.pin_clk, knob, on_rotate)))
        tasks.append(asyncio.create_task(catch_button_toggle(knob)))
    
    await asyncio.gather(*tasks)

async def catch_interrupt(pin, knob, onChange):
    while True:
        new_state = knob.pin_clk.value
        
        if new_state != knob.button_clk_value:
            knob.button_clk_value = new_state
            await onChange(knob, new_state)
        
        await asyncio.sleep(SLEEP)
    
async def catch_button_toggle(knob):
    last_state = False
    
    while True:
        # prints different values when (not) clicked depending on rotating state
        max_val = BUTTON_MAX_VAL_CLK_TRUE if knob.button_clk_value else BUTTON_MAX_VAL_CLK_FALSE
        new_state = knob.pin_sw.value < max_val

        # debug
        #print(f"{knob.name} - {knob.pin_sw.value} {knob.button_clk_value} {new_state} {max_val}")
        
        # State changed
        if new_state != last_state:
            last_state = new_state
            
            # Use time to make sure it was pressed (fix inconsistent states)
            if not new_state:
                knob.button_toggle_time = time.monotonic()
            else:
                # Released button
                if knob.button_toggled:
                    knob.button_toggled = False
                    await on_button_release(knob)
                
                knob.button_toggle_time = 0
        
        # Make sure button is humanly pressed for min x ms
        else:
            if knob.button_toggle_time != 0 and not knob.button_toggled and (time.monotonic() - knob.button_toggle_time) > BUTTON_MIN_HOLD:
                knob.button_toggled = True
                await on_button_press(knob)
        
        await asyncio.sleep(SLEEP)

asyncio.run(main())
