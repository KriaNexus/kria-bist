﻿# BIST PWM Test Module

## Overview

This test module verifies the PWM functionality on the AMD Kria&trade; starter kits.

## Tests

The PWM module contains a single functional test, which requires user input.
This test prompts you to reduce the fan speed. It then reduces the fan
speed by writing a small value to the pwm device to which the fan is connected.
The user is then asked to verify that the fan is spinning at a slower speed. If
it is, the fan is set back to the max speed by writing a value of 255 to the
pwm device. You are then asked to verify that the fan is spinning at full
speed and if you confirm, the test passes. If at any point in this flow, you indicate that the fan is not behaving as expected, the test fails.

## Test Execution

The example commands for this module are provided below (KV260):

```bash
pytest-3 --board kv260 -m pwm		// Run all tests in this module
pytest-3 --board kv260 -k fan		// Run fan test
```

## Test Debug

* Make sure that the fancontrol service has been stopped before running this test.
* Make sure that the BIST firmware is loaded.
* Make sure that the fan is connected to the J13 connecter.

## Known Issues and Limitations

* The fan test is limited to the pwm device and channel for the fan.

## Next Steps

1. [BIST Overview](../overview)


<p class="sphinxhide" align="center"><sub>Copyright © 2023 Advanced Micro Devices, Inc</sub></p>

<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
