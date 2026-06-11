# weather.py — Weather system (Upgrade 10) ───────────────────────────────────
"""
Weather affects every EV uniformly:
  - speed_mult  : multiplies EV_Speed (movement tick threshold), so higher
                  values mean MORE ticks needed per cell move = SLOWER.
  - drain_mult  : multiplies battery drain per step.

Weather changes randomly every WEATHER_CHANGE_INTERVAL frames.
"""
import random
from config import (WEATHER_SUNNY, WEATHER_RAINY, WEATHER_STORM,
                     WEATHER_NAMES, WEATHER_SPEED_MULT, WEATHER_DRAIN_MULT,
                     WEATHER_CHANGE_INTERVAL)

current_weather = [WEATHER_SUNNY]

_WEATHER_SEQUENCE_WEIGHTS = (
    [WEATHER_SUNNY]*5 + [WEATHER_RAINY]*3 + [WEATHER_STORM]*2
)

def update_weather(frame):
    if frame > 0 and frame % WEATHER_CHANGE_INTERVAL == 0:
        current_weather[0] = random.choice(_WEATHER_SEQUENCE_WEIGHTS)
        return True
    return False

def speed_mult():
    return WEATHER_SPEED_MULT[current_weather[0]]

def drain_mult():
    return WEATHER_DRAIN_MULT[current_weather[0]]

def name():
    return WEATHER_NAMES[current_weather[0]]
